"""Local real-model case study. Production sources are loaded without edits.
20-ms offline event replay; computation measured, call time simulated. No network/UI.
"""
from __future__ import annotations
import argparse,hashlib,importlib,json,os,sys,time,platform,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SR=16000; FRAME=320; EXPECTED='ae78eb6ed8e343dedd72351d942a27718eced82f355a90ef7583334a203beec0'

def sha(p): return hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
def dump(p,obj): Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def modules(version):
    for n in ['audio_window','risk','scoring']: sys.modules.pop(n,None)
    sys.path.insert(0,str(ROOT/'snapshots'/version))
    try: return importlib.import_module('scoring'),importlib.import_module('risk')
    finally: sys.path.pop(0)

def state(payload,version,now):
    e=payload.get('deepfake',{})
    if payload.get('type')!='risk': v=payload.get('state','waiting')
    elif version=='current': v=e['state']
    elif e['level']=='high' and e['updates']>=3: v='ai'
    elif e['level']=='elevated': v='uncertain'
    elif e['level']=='listening' and e['human_steps']>=3: v='human'
    else: v='analyzing'
    backend=v
    if version=='current' and now>=15 and v in ['analyzing','waiting']:v='uncertain'
    return dict(backend_state=backend,state=v,score=e.get('score'),recent_ai=e.get('recent_ai',False),updates=e.get('updates',0),p_smoothed=e.get('p_smoothed'),logit_smoothed=e.get('logit_smoothed'))

def summarize(timeline,windows,duration,labels):
    # Right-continuous states at all event/frame boundaries; no future row for milestones.
    first=lambda key,value: next((r['t'] for r in timeline if r[key]==value),None)
    duration_of=lambda pred: sum((b['t']-a['t']) for a,b in zip(timeline,timeline[1:]) if pred(a))
    milestones={str(t):dict(next(r for r in reversed(timeline) if r['t']<=t)) for t in [5,10,15,20,30] if t<=duration}
    changes=[]
    for r in timeline:
        if not changes or (r['state'],r['recent_ai'])!=(changes[-1]['state'],changes[-1]['recent_ai']):changes.append(r)
    ai_intervals=[(x['start'],x['end']) for x in labels if x['label']=='ai']
    def overlap_ai(a,b):return sum(max(0,min(b,e)-max(a,s)) for s,e in ai_intervals)
    incorrect_human=sum(overlap_ai(a['t'],b['t']) for a,b in zip(timeline,timeline[1:]) if a['state']=='human')
    human_intervals=[(x['start'],x['end']) for x in labels if x['label']=='human']
    false_ai=sum(sum(max(0,min(b['t'],e)-max(a['t'],s)) for s,e in human_intervals) for a,b in zip(timeline,timeline[1:]) if a['state']=='ai')
    transitions=[]
    for lab in labels:
        start,end=lab['start'],lab['end']; target=lab['label']
        if target not in ['ai','human']:continue
        at=[r for r in timeline if start<=r['t']<end]
        transitions.append(dict(**lab,first_target_delay=next((round(r['t']-start,4) for r in at if r['state']==target),None),first_recent_ai_delay=next((round(r['t']-start,4) for r in at if r['recent_ai']),None),first_non_human_delay=next((round(r['t']-start,4) for r in at if r['state']!='human'),None)))
    ms=[w['infer_ms'] for w in windows]
    return dict(duration_sec=duration,window_count=len(windows),completed_count=sum(w.get('completed',False) for w in windows),first_ai=first('state','ai'),first_human=first('state','human'),first_recent_ai=first('recent_ai',True),incorrect_human_during_ai_sec=round(incorrect_human,4),false_ai_during_human_sec=round(false_ai,4),human_and_recent_ai_sec=round(duration_of(lambda r:r['state']=='human' and r['recent_ai']),4),milestones=milestones,final=timeline[-1],changes=changes,transitions=transitions,infer_ms={'median':float(np.median(ms)),'p95':float(np.percentile(ms,95)),'max':max(ms)} if ms else {})

def replay(detector,pcm,version,labels,case):
    scoring,_=modules(version); session=scoring.AudioScoringSession(detector,(detector.meta['threshold_eer'],detector.meta['threshold_1pct_fpr']))
    windows=[];timeline=[dict(t=0,**state(session.payload(0),version,0))];pending=None;next_score=1.;mapping=np.full(64000,-1,np.int64)
    for i in range(0,len(pcm),FRAME):
        frame=pcm[i:i+FRAME];now=(i+len(frame))/SR
        # Async worker completion before this frame. refresh at actual simulated completion.
        if pending and pending[0]<=now+1e-9:
            done,result,generation,idx=pending;session.refresh(done);session.complete(result,generation)
            windows[idx]['completed']=True;windows[idx]['completed_at']=done;windows[idx]['completion_payload']=session.payload(done)
            timeline.append(dict(t=round(done,6),**state(session.payload(done),version,done)));pending=None
        session.push(frame.tobytes(),now)
        voiced=np.sqrt(np.mean((frame.astype(np.float32)/32768)**2))>=.01
        if version=='current' or voiced:
            n=len(frame);mapping[:-n]=mapping[n:];mapping[-n:]=np.arange(i,i+n)
        if now+1e-9>=next_score and pending is None:
            next_score=now+1.
            snap=session.snapshot(now)
            if snap is not None:
                audio,generation=snap;ids=mapping[-len(audio):];valid=ids[ids>=0]
                # Preserve disjoint intervals: baseline drops pauses, current retains them.
                cuts=np.flatnonzero(np.diff(valid)!=1)+1; chunks=np.split(valid,cuts)
                intervals=[[float(c[0]/SR),float((c[-1]+1)/SR)] for c in chunks if len(c)]
                assert len(valid)==len(audio) and np.array_equal(audio, pcm[valid].astype(np.float32)/32768), 'Source interval mapping mismatch'
                result=detector.score_window(audio)
                w=dict(submitted_at=round(now,6),audio_intervals=intervals,input_samples=len(audio),input_sha256=hashlib.sha256(audio.tobytes()).hexdigest(),preprocessing_repeats_partial=len(audio)<64000,weight=getattr(session,'pending_weight',1.),completed=False,**result)
                windows.append(w);pending=(now+result['infer_ms']/1000,result,generation,len(windows)-1)
                print(f'{case} {version} {now:.2f} z={result["logit"]:.3f} {result["infer_ms"]:.0f}ms',flush=True)
        timeline.append(dict(t=round(now,6),**state(session.payload(now),version,now)))
    # Real agent cancels in-flight inference when stream ends. Never flush it into call verdict.
    duration=len(pcm)/SR
    timeline=compact(timeline,labels,duration)
    return dict(summary=summarize(timeline,windows,duration,labels),windows=windows,timeline=timeline)

def matched(detector,source,version,labels,duration):
    _,risk=modules(version);eng=risk.RiskEngine(detector.meta['threshold_eer'],detector.meta['threshold_1pct_fpr']) if version=='baseline' else risk.CallEvidenceEngine(detector.meta['threshold_eer'],detector.meta['threshold_1pct_fpr'])
    timeline=[dict(t=0,**state({'type':'status','state':'analyzing'},version,0))];ws=[]
    for w in source:
        if not w['completed']:continue
        e=eng.update(w['p_fake'],w['logit']) if version=='baseline' else eng.update(w['p_fake'],w['logit'],w['weight'])
        t=w['completed_at'];timeline.append(dict(t=t,**state({'type':'risk','deepfake':e},version,t)));ws.append(w)
    if version=='current' and duration>=15 and not any(r['t']<=15 and r['updates']>=2 for r in timeline):
        at15=next(r for r in reversed(timeline) if r['t']<=15);timeline.append(dict(**{k:v for k,v in at15.items() if k not in ['t','state']},t=15,state='uncertain'));timeline.sort(key=lambda r:r['t'])
    timeline.append(dict(t=duration,**{k:v for k,v in timeline[-1].items() if k!='t'}));timeline=compact(timeline,labels,duration)
    return dict(summary=summarize(timeline,ws,duration,labels),windows=ws,timeline=timeline)

def compact(timeline,labels,duration):
    # Keep each changed assessment, exact label boundaries, and the call end.
    timeline.sort(key=lambda r:r['t']);out=[]
    for r in timeline:
        if not out or {k:v for k,v in r.items() if k!='t'}!={k:v for k,v in out[-1].items() if k!='t'}:out.append(r)
    for t in sorted({0,duration,*[lab['start'] for lab in labels]}):
        if not any(abs(r['t']-t)<1e-8 for r in out):
            a=next(r for r in reversed(timeline) if r['t']<=t);out.append(dict(a,t=t))
    return sorted(out,key=lambda r:r['t'])

def pcm(x):return (np.clip(x,-1,1)*32767).astype(np.int16)
def band(x):return resample_poly(resample_poly(x,1,2),2,1)[:len(x)].astype(np.float32)
def g711(x):
    # ITU G.711 mu-law via libsndfile PCM16 -> ULAW WAV -> decoded float (real companding).
    import io
    b=io.BytesIO();sf.write(b,band(x)[::2],8000,format='WAV',subtype='ULAW');b.seek(0);y,s=sf.read(b,dtype='float32')
    assert s==8000
    return resample_poly(y,2,1)[:len(x)].astype(np.float32)
def conditions(x):
    rng=np.random.default_rng(20261022);out={'original':x,'8khz_bandwidth_only':band(x),'g711_mulaw':g711(x),'low_volume_minus20dB':x*.1,'mild_clipping':np.clip(x / np.quantile(np.abs(x), .99),-1,1)}
    for snr in [30,20,10]:
        n=rng.standard_normal(len(x)).astype(np.float32);n*=np.sqrt(np.mean(x*x)/(10**(snr/10)*np.mean(n*n)));out[f'white_noise_{snr}dB_SNR']=x+n
    for gap in [2,10]:out[f'pause_{gap}s_after_16s']=np.concatenate([x[:16*SR],np.zeros(gap*SR,np.float32),x[16*SR:]])
    return out

class MeasuredDetector:
    def __init__(self,weights,device):
        from transformers import Wav2Vec2Config
        original=Wav2Vec2Config.from_pretrained
        # Resolve original base config locally: same JSON, no architecture substitution.
        Wav2Vec2Config.from_pretrained=classmethod(lambda cls,base,*a,**kw:original(str(ROOT/'snapshots/architecture'),*a,**kw))
        sys.path.insert(0,str(ROOT/'snapshots/current'));import detector_adapter
        detector_adapter.WEIGHTS_DIR=str(weights);os.environ['DETECTOR_DEVICE']=device
        t=time.perf_counter();self.inner=detector_adapter.RealDetector();self.startup_sec=time.perf_counter()-t
        self.meta=self.inner.meta;self.device=self.inner.device;self.cache={};self.hits=0;self.misses=0
    def score_window(self,a):
        key=hashlib.sha256(a.tobytes()).hexdigest()
        if key in self.cache:self.hits+=1  # Count repeated input, but execute inference again.
        r=self.inner.score_window(a);self.misses+=1;self.cache[key]=r
        return dict(**r,cache_reused=False)

def main():
    global np,sf,resample_poly
    parser=argparse.ArgumentParser();parser.add_argument('--device',default='mps');parser.add_argument('--only-original',action='store_true');args=parser.parse_args()
    start=time.perf_counter()
    import numpy as np, soundfile as sf,torch
    from scipy.signal import resample_poly
    if sha('/Users/spatel7/Downloads/best.pt')!=EXPECTED:raise RuntimeError('checkpoint mismatch')
    weights=ROOT/'weights';weights.mkdir(exist_ok=True)
    (weights/'detector_config.json').write_bytes((ROOT/'snapshots/current/model/detector_config.json').read_bytes())
    if not (weights/'best.pt').exists():(weights/'best.pt').symlink_to('/Users/spatel7/Downloads/best.pt')
    # inference.py lookup remains exact source; only its configuration resolution is local.
    sys.path.insert(0,str(ROOT/'snapshots/current/model'))
    detector=MeasuredDetector(weights,args.device)
    print('LOADED',detector.device,detector.startup_sec,flush=True)
    p=Path('/Users/spatel7/Downloads/ElevenLabs_2026-10-23T01_11_44_shrey_ivc_sp100_s50_sb75_v4.mp3');x,sr=sf.read(p,dtype='float32',always_2d=True);assert sr==44100, 'This pinned recording must be 44.1 kHz';x=x.mean(1);x=resample_poly(x,160,441).astype(np.float32)
    decoded_duration=len(x)/SR
    cases=conditions(x);label_overrides={}
    if args.only_original:cases={'original':x}
    sources={}; human_files=sorted((ROOT/'audio/human_controls').glob('librispeech_test_clean_*_40s.wav'))
    for hp in human_files:
        h,s=sf.read(hp,dtype='float32',always_2d=True);h=h.mean(1)
        if s!=SR:
            from math import gcd
            g=gcd(s,SR);h=resample_poly(h,SR//g,s//g).astype(np.float32)
        h=h[:40*SR];cases[hp.stem]=h;sources[hp.stem]=dict(path=str(hp.relative_to(ROOT)),sha256=sha(hp))
    # Transitions use first verified control; repeated 60s intro is explicitly related audio.
    if human_files and not args.only_original:
        h=cases[human_files[0].stem];intro=np.tile(h,int(np.ceil(60*SR/len(h))))[:60*SR]
        cases['human60_then_ai']=np.concatenate([intro,x]);cases['ai_then_human']=np.concatenate([x,h])
        # Additional targeted diagnostics chosen after first controls run; not independent validation.
        h2=cases[human_files[1].stem];prefix=h2[:16*SR];intro2=np.tile(prefix,4)[:60*SR]
        cases['diagnostic_human16_then_ai']=np.concatenate([prefix,x])
        cases['diagnostic_human_prefix60_then_ai']=np.concatenate([intro2,x])
        cases['diagnostic_human_prefix120_then_ai']=np.concatenate([np.tile(prefix,8)[:120*SR],x])
        cases['diagnostic_ai_then_human6930']=np.concatenate([x,h2])
        for name,split in [('diagnostic_human16_then_ai',16),('diagnostic_human_prefix60_then_ai',60),('diagnostic_human_prefix120_then_ai',120)]:label_overrides[name]=[dict(start=0,end=split,label='human'),dict(start=split,end=len(cases[name])/SR,label='ai')]
        label_overrides['diagnostic_ai_then_human6930']=[dict(start=0,end=len(x)/SR,label='ai'),dict(start=len(x)/SR,end=len(cases['diagnostic_ai_then_human6930'])/SR,label='human')]
    report={'kind':'real_model_related_recordings_case_study','baseline_commit':'dca989c3126be4778638a002d3355a463f8789eb','updated_commit':'ec2f4dd80de433f176b1d9f90a20ca35d60707aa','architecture_revision':'1a640f32ac3e39899438a2931f9924c02f080a54','device':detector.device,'startup_including_zero_warmup_sec':detector.startup_sec,'checkpoint_sha256':EXPECTED,'architecture_sha256':sha(ROOT/'cache/architecture/config.json'),'audio_sha256':sha(p),'source_audio':str(p),'source_duration_sec':len(sf.read(p,dtype='float32')[0])/sr,'mp3_header_duration_sec':sf.info(p).duration,'resampled_duration_sec':decoded_duration,'original_sr':sr,'frame_ms':20,'scheduler':'agent default 1-second attempts; one in flight; completion at measured latency; cancellation at call end','network_latency_sec':0,'human_controls':sources,'cases':{}}
    for name,signal in cases.items():
        dur=len(signal)/SR
        if name in label_overrides:labels=label_overrides[name]
        elif name.startswith('human60'):labels=[dict(start=0,end=60,label='human'),dict(start=60,end=dur,label='ai')]
        elif name=='ai_then_human':labels=[dict(start=0,end=len(x)/SR,label='ai'),dict(start=len(x)/SR,end=dur,label='human')]
        elif name in sources:labels=[dict(start=0,end=dur,label='human')]
        elif name.startswith('pause_'):
            gap=int(name.split('_')[1][:-1]);labels=[dict(start=0,end=16,label='ai'),dict(start=16,end=16+gap,label='silence'),dict(start=16+gap,end=dur,label='ai')]
        else:labels=[dict(start=0,end=dur,label='ai')]
        row={'labels':labels,'pcm_sha256':hashlib.sha256(pcm(signal).tobytes()).hexdigest(),'rms':float(np.sqrt(np.mean(signal**2))),'clip_fraction':float(np.mean(np.abs(signal)>=.99)),'production':{},'matched':{}}
        for version in ['baseline','current']:row['production'][version]=replay(detector,pcm(signal),version,labels,name)
        # Common eligible segments = updated session's actual submissions. No recomputed/random logits.
        for version in ['baseline','current']:row['matched'][version]=matched(detector,row['production']['current']['windows'],version,labels,dur)
        report['cases'][name]=row
        dump(ROOT/'results/real_audio_results.json',report)
    report['actual_model_inferences']=detector.misses;report['unique_input_count']=len(detector.cache);report['repeated_inputs']=detector.hits;report['cache_hits']=0;report['wall_sec']=time.perf_counter()-start
    report['environment']={'python':platform.python_version(),'platform':platform.platform(),'torch':torch.__version__,'numpy':np.__version__,'mps_available':torch.backends.mps.is_available(),'cpu_threads':torch.get_num_threads()}
    dump(ROOT/'results/real_audio_results.json',report);dump(ROOT/'results/inference_cache.json',detector.cache)
    rows=[]
    for case,cr in report['cases'].items():
        for mode in ['production','matched']:
            for version,r in cr[mode].items():
                s=r['summary'];rows.append(dict(case=case,mode=mode,version=version,first_ai=s['first_ai'],first_human=s['first_human'],first_recent_ai=s['first_recent_ai'],at15=s['milestones'].get('15',{}).get('state'),final=s['final']['state'],score=s['final']['score'],incorrect_human_sec=s['incorrect_human_during_ai_sec'],false_ai_sec=s['false_ai_during_human_sec'],windows=s['window_count'],median_infer_ms=s['infer_ms'].get('median')))
    with (ROOT/'results/summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print('DONE',report['wall_sec'],detector.misses,detector.hits,flush=True)
if __name__=='__main__':main()
