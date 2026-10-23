"""Versioned development benchmark. Never writes frozen evaluation artifacts.

Window selection runs real inference. Aggregation-only factors reuse precisely the
completed windows, logits, weights and timestamps from that selection. These are
related development recordings, never independent window/call accuracy estimates.
"""
from __future__ import annotations
import argparse, csv, hashlib, importlib, importlib.util, json, math, os
from pathlib import Path
import platform, random, shutil, subprocess, sys, time

HERE = Path(__file__).resolve().parent
EVAL = HERE.parent
REPO = EVAL.parent
MODULES = ('audio_window', 'risk', 'scoring', 'current_evidence', 'risk_protocol', 'pipeline_config')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def load_modules(directory):
    for name in MODULES:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(directory))
    try:
        return importlib.import_module('scoring'), importlib.import_module('risk')
    finally:
        sys.path.pop(0)


def frozen_paths():
    files = [EVAL / n for n in ('README.md', 'regression_report.md', 'evaluate.py', 'report.py', 'dependencies.txt')]
    return sorted(files + [p for folder in ('results', 'snapshots') for p in (EVAL / folder).rglob('*')
                           if p.is_file() and '__pycache__' not in p.parts])


def verify_baseline():
    manifest = json.loads((HERE / 'frozen_baseline_manifest.json').read_text())
    errors = [p for p, expected in manifest['sha256'].items() if not (EVAL / p).is_file() or sha(EVAL / p) != expected]
    if errors:
        raise RuntimeError('Frozen baseline changed: ' + ', '.join(errors))
    return manifest


def legacy():
    spec = importlib.util.spec_from_file_location('frozen_evaluate', EVAL / 'evaluate.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import numpy as np, soundfile as sf
    from scipy.signal import resample_poly
    mod.np, mod.sf, mod.resample_poly = np, sf, resample_poly
    return mod


def decode(path, target=16000):
    import numpy as np, soundfile as sf
    from scipy.signal import resample_poly
    x, rate = sf.read(path, dtype='float32', always_2d=True)
    if not isinstance(rate, int) or rate <= 0 or not len(x) or not np.isfinite(x).all():
        raise ValueError(f'Invalid decoded audio: {path}')
    meta = dict(path=str(Path(path).resolve()), sha256=sha(path), decoded_sample_rate=rate,
                decoded_frames=len(x), channels=x.shape[1], decoded_duration_sec=len(x) / rate)
    x = x.mean(1)
    if rate != target:
        g = math.gcd(rate, target)
        x = resample_poly(x, target // g, rate // g).astype(np.float32)
    return x, meta


def make_cases(args, config, out):
    import numpy as np
    old = legacy()
    old.SR = config['sample_rate']
    x, xm = decode(args.ai_audio)
    cases = {}; sources = {'ai_source': xm}; unknown = []
    def add(name, signal, labels, groups, condition):
        cases[name] = dict(signal=signal, labels=labels, source_groups=groups,
                           condition=condition, partition='development', independent=False)
    for name, signal in old.conditions(x).items():
        labels = [dict(start=0., end=len(signal)/16000, label='ai')]
        if name.startswith('pause_'):
            gap = int(name.split('_')[1][:-1]); labels = [dict(start=0., end=16., label='ai'),dict(start=16.,end=16.+gap,label='silence'),dict(start=16.+gap,end=len(signal)/16000,label='ai')]
        add(name, signal, labels, ['ai_source'], name)
    for extra_path in args.extra_ai:
        extra,meta=decode(extra_path);group='supplemental_ai_'+extra_path.stem
        sources[group]={**meta,'provenance_status':'user-supplied ElevenLabs filename; identity, consent and training overlap unverified','synthetic_system':'ElevenLabs; same system as original; not held-out'}
        for condition,signal in old.conditions(extra).items():
            labels=[dict(start=0.,end=len(signal)/16000,label='ai')]
            if condition.startswith('pause_'):
                gap=int(condition.split('_')[1][:-1]);labels=[dict(start=0.,end=16.,label='ai'),dict(start=16.,end=16.+gap,label='silence'),dict(start=16.+gap,end=len(signal)/16000,label='ai')]
            add(group+'__'+condition,signal,labels,[group],condition)
    humans = []
    for hp in args.human_audio:
        h, hm = decode(hp); h = h[:40*16000]; name = Path(hp).stem
        sources[name] = hm; humans.append((name,h))
        add(name,h,[dict(start=0.,end=len(h)/16000,label='human')],[name],'original')
    if len(humans) >= 2:
        n,h = humans[0]; n2,h2 = humans[1]; prefix = h2[:16*16000]
        for name,intro,group in [('human60_then_ai', np.tile(h,math.ceil(60*16000/len(h)))[:60*16000],n),('diagnostic_human16_then_ai',prefix,n2),('diagnostic_human_prefix60_then_ai',np.tile(prefix,4)[:60*16000],n2),('diagnostic_human_prefix120_then_ai',np.tile(prefix,8)[:120*16000],n2)]:
            s = np.concatenate([intro,x]); split=len(intro)/16000
            add(name,s,[dict(start=0.,end=split,label='human'),dict(start=split,end=len(s)/16000,label='ai')],[group,'ai_source'],'constructed_transition')
        for name,group,human in [('ai_then_human',n,h),('diagnostic_ai_then_human6930',n2,h2)]:
            s=np.concatenate([x,human]);split=len(x)/16000
            add(name,s,[dict(start=0.,end=split,label='ai'),dict(start=split,end=len(s)/16000,label='human')],['ai_source',group],'constructed_transition')
    else:
        unknown.append('Two human controls required for all 18 named transition regressions')
    if config.get('extended_controls'):
        for name,h in humans:
            for condition,s in old.conditions(h).items():
                if condition == 'original': continue
                # Conditions include inserted pauses; labels preserve those non-speech intervals.
                labels=[dict(start=0.,end=len(s)/16000,label='human')]
                if condition.startswith('pause_'):
                    gap=int(condition.split('_')[1][:-1]);labels=[dict(start=0.,end=16.,label='human'),dict(start=16.,end=16.+gap,label='silence'),dict(start=16.+gap,end=len(s)/16000,label='human')]
                add(name+'__'+condition,s,labels,[name],condition)
            ffmpeg=shutil.which('ffmpeg')
            if ffmpeg:
                mp3=out/(name+'__128kbps_44100.mp3')
                subprocess.run([ffmpeg,'-v','error','-i',sources[name]['path'],'-ar','44100','-b:a','128k',str(mp3)],check=True)
                s,m=decode(mp3);s=s[:40*16000];sources[name+'__mp3']=m
                add(name+'__mp3_128kbps_44100',s,[dict(start=0.,end=len(s)/16000,label='human')],[name],'mp3_128kbps_44100')
            else: unknown.append(name+': ffmpeg unavailable; matched MP3 control missing')
        rng=np.random.default_rng(config['seed']); n=int(config['non_speech_duration_sec']*16000); t=np.arange(n)/16000
        white=rng.normal(size=n);freq=np.fft.rfftfreq(n,1/16000);pink=np.fft.irfft(np.fft.rfft(white)/np.sqrt(np.maximum(freq,1)),n)
        dtmf=(np.sin(2*np.pi*697*t)+np.sin(2*np.pi*1209*t))*((t%1)<.5)
        music=sum(np.sin(2*np.pi*f*t) for f in (220,277.18,329.63,440))*(.6+.4*np.sin(2*np.pi*2*t))
        add('control_silence',np.zeros(n,np.float32),[dict(start=0.,end=n/16000,label='non_speech')],['synthetic_silence'],'silence')
        for base,s in [('white_noise',white),('pink_noise',pink),('dtmf',dtmf),('synthetic_music',music)]:
            for rms in config['non_speech_rms_levels']:
                signal=(s/np.sqrt(np.mean(s*s))*rms).astype(np.float32)
                add(f'control_{base}_rms{rms}',signal,[dict(start=0.,end=n/16000,label='non_speech')],['synthetic_'+base],base)
        unknown += ['Real TV/background chatter and consented actual hold music were not supplied; synthetic music is a stress control only.']
    expected=list(json.loads((EVAL/'results/real_audio_results.json').read_text())['cases'])
    ordered={k:cases.pop(k) for k in expected if k in cases};ordered.update(cases)
    return ordered,sources,unknown


class Detector:
    def __init__(self,args,config):
        import numpy as np
        from transformers import Wav2Vec2Config
        original=Wav2Vec2Config.from_pretrained
        Wav2Vec2Config.from_pretrained=classmethod(lambda cls,base,*a,**kw:original(str(args.architecture_dir),*a,**kw))
        for name in ('detector_adapter','inference'): sys.modules.pop(name,None)
        sys.path.insert(0,str(args.model_source_dir)); sys.path.insert(0,str(args.current_dir))
        try:
            adapter=importlib.import_module('detector_adapter');adapter.WEIGHTS_DIR=str(args.model_dir)
            adapter.pick_device=lambda:args.device
            started=time.perf_counter();self.inner=adapter.RealDetector();self.startup_sec=time.perf_counter()-started
        finally:
            sys.path.pop(0);sys.path.pop(0);Wav2Vec2Config.from_pretrained=original
        self.meta=self.inner.meta;self.device=self.inner.device;self.calls=0
    def score_window(self,a):
        self.calls+=1
        return self.inner.score_window(a)


def quality(window):
    import numpy as np
    if hasattr(window,'rejection_reason') and window.rejection_reason:return window.rejection_reason
    if window.filled < getattr(window,'capacity',64000): return 'insufficient_audio'
    if hasattr(window,'clipped') and float(window.clipped.mean())>.05:return 'audio_distorted'
    speech=getattr(window,'speech',None)
    if speech is not None and np.count_nonzero(speech)<window.min_samples:return 'insufficient_usable_speech'
    if not window.ready(): return 'insufficient_usable_speech'
    return 'eligible_waiting_for_distinct_audio'


def selection(detector, signal, directory, kind, config, *, candidate=False, overlap_hop=None):
    """Real inference, source-sample mapping, one in flight, call-end cancellation."""
    import numpy as np
    scoring,_=load_modules(directory)
    opts={}
    if candidate:
        import inspect
        if not hasattr(scoring,'ScoringConfig'): raise RuntimeError('Candidate ScoringConfig unavailable')
        allowed=inspect.signature(scoring.ScoringConfig).parameters
        kw={'quiet_enabled':True,'current_enabled':False}
        opts['config']=scoring.ScoringConfig(**{k:v for k,v in kw.items() if k in allowed})
    session=scoring.AudioScoringSession(detector,(detector.meta['threshold_eer'],detector.meta['threshold_1pct_fpr']),**opts)
    capacity=session.window.capacity; mapping=np.full(capacity,-1,np.int64); windows=[];attempts=[];pending=None;next_score=1.;speech_events=[];frame_quality=[]
    for i in range(0,len(signal),config['frame_samples']):
        frame=signal[i:i+config['frame_samples']]; now=(i+len(frame))/16000
        if pending is not None and pending[0]<=now+1e-9:
            done,result,generation,idx=pending;session.refresh(done);session.complete(result,generation)
            accepted=session.pending_since is None and generation==session.generation
            windows[idx].update(completed=accepted,completed_at=done,publication_at=done if accepted else None,completion_reason='accepted' if accepted else 'stale_generation')
            pending=None
        before=session.window.total_voiced;session.push(frame.tobytes(),now)
        voiced=session.window.total_voiced>before;speech_events.append((now,voiced))
        rms=float(np.sqrt(np.mean((frame.astype(np.float32)/32768)**2)))
        diag=session.window.diagnostics() if hasattr(session.window,'diagnostics') else dict(frame_rms=rms,speech_decision=voiced,clipping_fraction=float(np.mean(np.abs(frame.astype(np.float32)/32768)>=.99)))
        frame_quality.append(dict(t=now,**diag))
        if kind!='baseline' or voiced:
            n=len(frame);mapping[:-n]=mapping[n:];mapping[-n:]=np.arange(i,i+n)
        if now+1e-9>=next_score and pending is None:
            next_score=now+config['score_interval_sec']
            # Development-only overlap: explicit hop changes selection; source influence
            # is bounded again by the current engine's genuinely new interval accounting.
            if overlap_hop is not None and hasattr(session,'last_scored_samples'):
                last_submit=windows[-1]['submitted_at'] if windows else None
                if last_submit is not None and now-last_submit+1e-9>=overlap_hop:
                    session.last_scored_samples=session.window.total_seen-capacity
            snap=session.snapshot(now)
            if snap is None:
                attempts.append(dict(t=now,submitted=False,reason=quality(session.window),estimated_speech_sec=getattr(session.window,'total_voiced',0)/16000))
                continue
            audio,generation=snap;ids=mapping[-len(audio):];valid=ids[ids>=0]
            cuts=np.flatnonzero(np.diff(valid)!=1)+1;chunks=np.split(valid,cuts)
            intervals=[[float(c[0]/16000),float((c[-1]+1)/16000)] for c in chunks if len(c)]
            if len(valid)!=len(audio) or not np.array_equal(audio,signal[valid].astype(np.float32)/32768):
                raise AssertionError('Source interval mapping mismatch')
            speech_mask=getattr(session.window,'speech',np.ones(capacity,dtype=np.bool_))[-len(audio):]
            usable_ids=valid[speech_mask]
            usable_cuts=np.flatnonzero(np.diff(usable_ids)!=1)+1
            usable_chunks=np.split(usable_ids,usable_cuts)
            usable_intervals=[[float(c[0]/16000),float((c[-1]+1)/16000)] for c in usable_chunks if len(c)]
            result=detector.score_window(audio)
            start=min(s for s,e in intervals);end=max(e for s,e in intervals)
            weight=getattr(session,'pending_weight',1.)
            windows.append(dict(window_id=len(windows),submitted_at=now,audio_intervals=intervals,usable_audio_intervals=usable_intervals,evidence_start_sec=start,evidence_end_sec=end,input_samples=len(audio),input_sha256=hashlib.sha256(audio.tobytes()).hexdigest(),preprocessing_repeats_partial=len(audio)<capacity,weight=float(weight),completed=False,completion_reason='cancelled_at_call_end',**result))
            attempts.append(dict(t=now,submitted=True,reason='submitted',estimated_speech_sec=getattr(session.window,'total_voiced',0)/16000))
            pending=(now+result['infer_ms']/1000,result,generation,len(windows)-1)
    return dict(windows=windows,attempts=attempts,speech_events=speech_events,duration_sec=len(signal)/16000,frame_quality=frame_quality,estimated_speech_sec=sum(voiced*min(config['frame_samples']/16000,t) for t,voiced in speech_events))


def display(row, policy, now, deadline=15.):
    row=dict(row)
    row['displayed_state']=row['state']
    if now>=deadline and row['state'] in ('analyzing','waiting'):row['displayed_state']='uncertain'
    if policy=='qualified_recent_warning' and row.get('recent_ai') and row['state']!='ai':
        row['displayed_state']='recent_warning'
    return row


def fresh_contribution(window,last_end):
    """Usable source samples in the new tail, including disjoint legacy inputs.

    Whole-window speech fraction remains untouched for reference aggregators.
    Candidate weight describes only the genuinely new source interval. Zero new
    usable speech is an explicit skipped contribution, never Human evidence.
    """
    start=max(window['evidence_start_sec'],last_end if last_end is not None else window['evidence_start_sec'])
    end=window['evidence_end_sec']
    usable=sum(max(0.,min(end,e)-max(start,s)) for s,e in window['usable_audio_intervals'])
    return dict(start_sec=start,end_sec=end,usable_sec=usable,weight=min(1.,usable/(end-start)) if end>start else 0.,accepted=usable>1e-9)


def aggregate(detector, source, directory, kind, config, candidate_mode=None):
    scoring,risk=load_modules(directory)
    thresholds=(detector.meta['threshold_eer'],detector.meta['threshold_1pct_fpr'])
    def engine():
        if candidate_mode:
            sys.path.insert(0,str(directory))
            try:
                current=importlib.import_module('current_evidence')
                settings=config['aggregation']
                return current.CurrentEvidenceEngine(*thresholds,horizon_sec=settings['candidate_horizon_sec'],mode=candidate_mode,entry_steps=settings['entry_steps'],recovery_steps=settings['recovery_steps'],min_segments=settings['min_segments'],min_usable_sec=settings['min_usable_sec'])
            finally:sys.path.pop(0)
        return risk.RiskEngine(*thresholds) if kind=='baseline' else risk.CallEvidenceEngine(*thresholds)
    eng=engine();last_candidate_end=None; pending=iter(sorted((w for w in source['windows'] if w['completed']),key=lambda w:w['completed_at'])); following=next(pending,None); last_speech=None
    old=legacy(); timeline=[];e=None
    for now,voiced in source['speech_events']:
        if kind=='baseline' and last_speech is not None and now-last_speech>=6.:
            eng=engine();e=None;last_speech=None
        if voiced:last_speech=now
        while following is not None and following['completed_at']<=now+1e-9:
            w=following;done=w['completed_at']
            if candidate_mode:
                contribution=fresh_contribution(w,last_candidate_end)
                w['candidate_contribution']=contribution
                if contribution['usable_sec']<=1e-9:
                    following=next(pending,None);continue
                e=eng.update(w['p_fake'],w['logit'],contribution['weight'],start_sec=w['evidence_start_sec'],end_sec=w['evidence_end_sec'])
                last_candidate_end=w['evidence_end_sec']
            elif kind=='baseline':e=eng.update(w['p_fake'],w['logit'])
            else:e=eng.update(w['p_fake'],w['logit'],w['weight'])
            row=old.state({'type':'risk','deepfake':e},'current' if candidate_mode or kind!='baseline' else 'baseline',done)
            timeline.append(dict(t=done,**display(row,config['display']['policy'],done)))
            following=next(pending,None)
        if candidate_mode:
            e=eng.snapshot(now)
            row=dict(backend_state=e['state'],state=e['state'],score=e.get('score'),recent_ai=e.get('recent_ai',False),updates=e.get('updates',0),freshness=e.get('freshness'),pending_state=e.get('pending_state'))
        elif e is None:row=old.state({'type':'status','state':'waiting' if kind=='baseline' else 'analyzing'},kind,now)
        else:row=old.state({'type':'risk','deepfake':e},kind,now)
        timeline.append(dict(t=now,**display(row,config['display']['policy'],now)))
    if not timeline:timeline=[dict(t=0,state='waiting',backend_state='waiting',displayed_state='waiting',recent_ai=False,score=None,updates=0)]
    initial=dict(timeline[0],t=0,state='waiting' if kind=='baseline' else 'analyzing',backend_state='waiting' if kind=='baseline' else 'analyzing',displayed_state='waiting' if kind=='baseline' else 'analyzing',recent_ai=False,score=None,updates=0)
    timeline.insert(0,initial)
    return timeline


def metrics(timeline, source, labels):
    duration=source['duration_sec'];states={'ai','human'}
    # Exact source label boundaries may fall inside a 20 ms frame. Carry the last
    # published state onto the boundary; never borrow a future completion.
    timeline=list(timeline)
    for boundary in sorted({x['start'] for x in labels}|{duration}):
        if not any(abs(r['t']-boundary)<1e-9 for r in timeline):
            prior=next(r for r in reversed(timeline) if r['t']<=boundary)
            timeline.append(dict(prior,t=boundary));timeline.sort(key=lambda r:r['t'])
    def overlap(a,b,label):return sum(max(0.,min(b,x['end'])-max(a,x['start'])) for x in labels if x['label']==label)
    totals={k:0. for k in ('incorrect_human_sec','backend_incorrect_human_sec','backend_human_with_warning_sec','false_ai_sec','false_warning_sec','warning_sec','abstention_sec','human_with_warning_sec','non_speech_confident_sec')}
    for a,b in zip(timeline,timeline[1:]):
        dt=max(0,b['t']-a['t']);state=a['displayed_state']
        if state=='human':totals['incorrect_human_sec']+=overlap(a['t'],b['t'],'ai')
        if a.get('state')=='human':totals['backend_incorrect_human_sec']+=overlap(a['t'],b['t'],'ai')
        if a.get('state')=='human' and a['recent_ai']:totals['backend_human_with_warning_sec']+=dt
        if state=='ai':totals['false_ai_sec']+=overlap(a['t'],b['t'],'human')
        if a['recent_ai']:
            totals['warning_sec']+=dt;totals['false_warning_sec']+=overlap(a['t'],b['t'],'human')
            if state=='human':totals['human_with_warning_sec']+=dt
        if state not in states:totals['abstention_sec']+=dt
        if state in states:totals['non_speech_confident_sec']+=overlap(a['t'],b['t'],'non_speech')
    transitions=[]
    for label in labels:
        target=label['label']
        if target not in states:continue
        rows=[r for r in timeline if label['start']<=r['t']<label['end']]
        transitions.append(dict(**label,target_delay_sec=next((r['t']-label['start'] for r in rows if r['displayed_state']==target),None),warning_delay_sec=next((r['t']-label['start'] for r in rows if r['recent_ai']),None),first_non_human_delay_sec=next((r['t']-label['start'] for r in rows if r['displayed_state']!='human'),None),outcome='reached_target' if any(r['displayed_state']==target for r in rows) else 'unknown_or_unreached'))
    warnings=[];active=None
    for row in timeline:
        if row['recent_ai'] and active is None:active=row['t']
        elif not row['recent_ai'] and active is not None:warnings.append(dict(start=active,end=row['t']));active=None
    if active is not None:warnings.append(dict(start=active,end=duration))
    for w in warnings:w['false_human_duration_sec']=overlap(w['start'],w['end'],'human')
    attempts=source['attempts']; completed=sum(w['completed'] for w in source['windows'])
    return dict(duration_sec=duration,**{k:round(v,6) for k,v in totals.items()},transitions=transitions,warning_events=warnings,false_warning_events=sum(w['false_human_duration_sec']>0 for w in warnings),submitted_count=len(source['windows']),completed_count=completed,cancelled_or_rejected_completion_count=len(source['windows'])-completed,published_count=completed,rejected_attempt_count=sum(not a['submitted'] for a in attempts),rejection_reasons={reason:sum(a['reason']==reason for a in attempts) for reason in sorted({a['reason'] for a in attempts if not a['submitted']})},analysis_coverage=completed>0,completed_window_coverage_fraction=completed/max(1,len(source['windows'])),assessment_coverage_fraction=round(1-totals['abstention_sec']/duration,6),estimated_speech_sec=source.get('estimated_speech_sec'),final=timeline[-1],at15=next((r for r in reversed(timeline) if r['t']<=15),None))


def compact(rows,labels):
    out=[]
    boundaries={x['start'] for x in labels}
    for r in rows:
        if not out or r['t'] in boundaries or {k:v for k,v in r.items() if k!='t'}!={k:v for k,v in out[-1].items() if k!='t'}:out.append(r)
    if out[-1]!=rows[-1]:out.append(rows[-1])
    return out


def run(args):
    import numpy as np, torch
    start=time.perf_counter();config=json.loads(args.config.read_text());verify_baseline()
    if args.output.exists():raise FileExistsError('Refusing to overwrite an existing run directory')
    args.output.mkdir(parents=True)
    # Freeze candidate Python sources before imports; another agent may edit the
    # working checkout while this intentionally long development run executes.
    candidate_original=args.candidate_dir
    candidate_frozen=args.output.resolve()/'sources'/'candidate'
    candidate_frozen.mkdir(parents=True)
    for source in candidate_original.glob('*.py'):shutil.copy2(source,candidate_frozen/source.name)
    args.candidate_dir=candidate_frozen
    shutil.copy2(Path(__file__),args.output/'runner.py')
    random.seed(config['seed']);np.random.seed(config['seed']);torch.manual_seed(config['seed'])
    for env in ('THRESHOLD_ELEVATED','THRESHOLD_HIGH'):
        if env in os.environ:raise RuntimeError(f'Undeclared environment override {env}; use versioned config')
    checkpoint=next((args.model_dir/n for n in ('detector_state.pt','best.pt') if (args.model_dir/n).exists()),None)
    if checkpoint is None:raise FileNotFoundError('Checkpoint missing')
    if sha(checkpoint)!=config['expected_checkpoint_sha256']:raise RuntimeError('Checkpoint hash mismatch')
    dump(args.output/'config.json',config)
    sources_dirs={'baseline':args.baseline_dir,'current':args.current_dir,'candidate':args.candidate_dir}
    metadata=dict(schema='trent-benchmark-v1',kind='related_source_development_real_model_replay',seed=config['seed'],benchmark_runner_sha256=sha(Path(__file__)),candidate_source_directory=str(candidate_original),source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),source_status=subprocess.check_output(['git','status','--porcelain'],cwd=REPO,text=True),config_sha256=sha(args.config),checkpoint_sha256=sha(checkpoint),model_config_sha256=sha(args.model_dir/'detector_config.json'),architecture_sha256=sha(args.architecture_dir/'config.json'),device=args.device,runtime=dict(python=sys.version,platform=platform.platform(),torch=torch.__version__,numpy=np.__version__,cpu_threads=torch.get_num_threads()),source_hashes={key:{str(p.relative_to(folder)):sha(p) for p in folder.rglob('*.py') if '__pycache__' not in p.parts} for key,folder in sources_dirs.items()},command=sys.argv,limitations=['Simulated call clock; measured inference completion; no network delay or disclosure delay.','Related transforms are grouped by original source; windows are not independent calls or speakers.','No independent held-out data or live calls supplied.','Synthetic controls do not replace real background chatter/music/TV.'],baseline_manifest_sha256=sha(HERE/'frozen_baseline_manifest.json'))
    freeze=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True);(args.output/'dependencies.lock.txt').write_text(freeze);metadata['dependency_lock_sha256']=sha(args.output/'dependencies.lock.txt')
    cases,sources,unknown=make_cases(args,config,args.output);metadata['sources']=sources;metadata['unknown_or_missing']=unknown
    expected=list(json.loads((EVAL/'results/real_audio_results.json').read_text())['cases']);metadata['named_regressions']={n:'present' if n in cases else 'missing' for n in expected}
    detector=Detector(args,config);metadata['startup_including_warmup_sec']=detector.startup_sec;dump(args.output/'metadata.json',metadata)
    report={'metadata':metadata,'cases':{},'synthetic_logic_checks':'Run benchmark/tests separately; not counted as real recordings.','independent_heldout':{'status':'not_evaluated','count':0},'live_call_results':{'status':'not_executed','count':0}}
    old=legacy()
    for name,case in cases.items():
        print('CASE',name,flush=True);signal=old.pcm(case.pop('signal'));case['pcm_sha256']=hashlib.sha256(signal.tobytes()).hexdigest();case['selections']={};case['experiments']={}
        for kind,directory in [('baseline',args.baseline_dir),('current',args.current_dir),('candidate_quiet',args.candidate_dir)]:
            if kind=='candidate_quiet' and args.no_candidate:continue
            selected=selection(detector,signal,directory,kind,config,candidate=kind=='candidate_quiet')
            quality_path=args.output/'quality'/name/(kind+'.jsonl');quality_path.parent.mkdir(parents=True,exist_ok=True)
            quality_path.write_text(''.join(json.dumps(r)+'\n' for r in selected.pop('frame_quality')))
            case['selections'][kind]={k:v for k,v in selected.items() if k!='speech_events'}
            case['selections'][kind]['frame_quality_path']=str(quality_path.relative_to(args.output))
            for agg,aggdir in [('baseline',args.baseline_dir),('current',args.current_dir)]:
                tl=aggregate(detector,selected,aggdir,agg,config);case['experiments'][kind+'__'+agg]=dict(metrics=metrics(tl,selected,case['labels']),timeline=compact(tl,case['labels']))
            if not args.no_candidate:
                for mode in config['aggregation']['candidates']:
                    tl=aggregate(detector,selected,args.candidate_dir,'current',config,candidate_mode=mode);case['experiments'][kind+'__candidate_'+mode]=dict(metrics=metrics(tl,selected,case['labels']),timeline=compact(tl,case['labels']))
        if not args.no_candidate and name in ('original','diagnostic_human_prefix120_then_ai','diagnostic_ai_then_human6930'):
            for hop in config.get('candidate_overlap_hops_sec',[]):
                key=f'candidate_quiet_overlap{hop:g}s';selected=selection(detector,signal,args.candidate_dir,'candidate_quiet',config,candidate=True,overlap_hop=hop)
                quality_path=args.output/'quality'/name/(key+'.jsonl');quality_path.parent.mkdir(parents=True,exist_ok=True)
                quality_path.write_text(''.join(json.dumps(r)+'\n' for r in selected.pop('frame_quality')))
                case['selections'][key]={k:v for k,v in selected.items() if k!='speech_events'}
                case['selections'][key]['frame_quality_path']=str(quality_path.relative_to(args.output))
                for mode in config['aggregation']['candidates']:
                    tl=aggregate(detector,selected,args.candidate_dir,'current',config,candidate_mode=mode);case['experiments'][key+'__candidate_'+mode]=dict(metrics=metrics(tl,selected,case['labels']),timeline=compact(tl,case['labels']))
        report['cases'][name]=case;dump(args.output/'results.json',report)
    metadata.update(actual_model_inferences=detector.calls,wall_sec=time.perf_counter()-start);dump(args.output/'metadata.json',metadata);dump(args.output/'results.json',report)
    report['frozen_reproduction']=compare_frozen(report);dump(args.output/'frozen_reproduction.json',report['frozen_reproduction']);dump(args.output/'results.json',report)
    write_tables(report,args.output);verify_baseline()
    print('DONE',metadata['wall_sec'],detector.calls,flush=True)


def compare_frozen(report):
    frozen=json.loads((EVAL/'results/real_audio_results.json').read_text())
    checks=[]
    for name,reference in frozen['cases'].items():
        case=report['cases'].get(name)
        if case is None:
            checks.append(dict(case=name,status='missing',passed=False));continue
        for selection_name in ('baseline','current'):
            expected=reference['production'][selection_name]['windows'];actual=case['selections'][selection_name]['windows']
            same_input=len(expected)==len(actual) and all(a['input_sha256']==b['input_sha256'] and a['audio_intervals']==b['audio_intervals'] for a,b in zip(expected,actual))
            same_completion=len(expected)==len(actual) and all(a['completed']==b['completed'] for a,b in zip(expected,actual))
            max_logit_error=max((abs(a['logit']-b['logit']) for a,b in zip(expected,actual)),default=0.)
            checks.append(dict(case=name,selection=selection_name,passed=same_input and same_completion and max_logit_error<=.01,exact_input_hashes_and_intervals=same_input,same_completion_semantics=same_completion,max_logit_abs_error=max_logit_error,reference_count=len(expected),actual_count=len(actual)))
    return dict(kind='frozen_input_logits_completion_reproduction',tolerance_logit=.01,passed=all(c['passed'] for c in checks),checks=checks,notes='Inference completion times are measured again; display policy is intentionally separate. No frozen artifacts were rewritten.')


def write_tables(report,out):
    rows=[];windows=[]
    for name,case in report['cases'].items():
        for mode,exp in case['experiments'].items():
            m=exp['metrics'];rows.append(dict(case=name,source_groups=';'.join(case['source_groups']),experiment=mode,submitted=m['submitted_count'],completed=m['completed_count'],cancelled=m['cancelled_or_rejected_completion_count'],rejected=m['rejected_attempt_count'],coverage=m['analysis_coverage'],incorrect_human_sec=m['incorrect_human_sec'],false_ai_sec=m['false_ai_sec'],false_warning_sec=m['false_warning_sec'],abstention_sec=m['abstention_sec'],non_speech_confident_sec=m['non_speech_confident_sec'],final=m['final']['displayed_state']))
        for selection_name,selection_data in case['selections'].items():
            for w in selection_data['windows']:windows.append(dict(case=name,selection=selection_name,**{k:w.get(k) for k in ('window_id','submitted_at','completed_at','completed','completion_reason','logit','p_fake','weight','input_sha256')},audio_intervals=json.dumps(w['audio_intervals'])))
    for filename,data in [('summary.csv',rows),('per_window.csv',windows)]:
        if data:
            with (out/filename).open('w') as f:writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    text=['# Development benchmark run','','This is a real-model replay of related development recordings. It is not an independent accuracy or release benchmark.','','## Real-model replay','','All old/new selection × old/new aggregation cells reuse the exact completed outputs within each selection. Changed input selection invokes real inference. Quiet and overlap experiments remain development candidates.','','See `summary.csv`, `per_window.csv` and `results.json` for exact inputs, transitions, warning persistence, abstention, rejected attempts, completion and coverage.','','| Case | Experiment | Inputs/completed | Incorrect Human (s) | False AI (s) | False warning (s) | Final |','|---|---|---:|---:|---:|---:|---|']
    for r in rows:text.append(f"| {r['case']} | {r['experiment']} | {r['submitted']}/{r['completed']} | {r['incorrect_human_sec']:.2f} | {r['false_ai_sec']:.2f} | {r['false_warning_sec']:.2f} | {r['final']} |")
    text+=['','## Synthetic logic checks','','Unit tests are separate from real-model replay. Their results are recorded in `logic_checks.txt` when run.','','## Independent held-out and live-call results','','Neither was available or executed. Missing sources, TV/chatter/consented hold music, training overlap, calibration, live phone timing and population release budgets remain unknown. No candidate is selected for production by these reused examples.','']
    (out/'report.md').write_text('\n'.join(text))


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=HERE/'configs/development.json')
    p.add_argument('--ai-audio',type=Path,required=True);p.add_argument('--extra-ai',type=Path,action='append',default=[]);p.add_argument('--human-audio',type=Path,nargs='+',required=True)
    p.add_argument('--model-dir',type=Path,required=True);p.add_argument('--model-source-dir',type=Path,default=EVAL/'snapshots/current/model')
    p.add_argument('--architecture-dir',type=Path,default=EVAL/'snapshots/architecture')
    p.add_argument('--baseline-dir',type=Path,default=EVAL/'snapshots/baseline');p.add_argument('--current-dir',type=Path,default=EVAL/'snapshots/current')
    p.add_argument('--candidate-dir',type=Path,default=REPO/'backend/AI Deepfake Pipeline/LiveKit Setup')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--device',choices=['mps','cpu','cuda'],default='cpu');p.add_argument('--no-candidate',action='store_true')
    return p

if __name__=='__main__':run(parser().parse_args())
