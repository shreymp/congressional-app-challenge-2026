"""Paired, deterministic model-only comparison. No production files are modified."""
from __future__ import annotations
import argparse, csv, gc, hashlib, importlib.util, json, math, os
from pathlib import Path
import platform, subprocess, sys, time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['MPLCONFIGDIR'] = str(ROOT / 'logs/matplotlib')
sys.dont_write_bytecode = True
import numpy as np

def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def dump(p, x):
    Path(p).write_text(json.dumps(x, indent=2, allow_nan=False) + '\n')

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def csvwrite(path, rows):
    if not rows: return
    with Path(path).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def thresholds(meta):
    return {k: float(meta.get('logit_' + k, math.log(meta[k] / (1-meta[k]))))
            for k in ('threshold_eer', 'threshold_1pct_fpr')}

def prepare():
    import soundfile as sf
    from scipy.signal import resample_poly
    helper = module('benchmark_source', ROOT/'sources/run.py')
    helper.EVAL = EVAL; helper.HERE = EVAL/'benchmark'
    helper.verify_baseline()
    legacy = module('legacy_source', ROOT/'sources/evaluate.py')
    legacy.np = np; legacy.sf = sf; legacy.resample_poly = resample_poly
    helper.legacy = lambda: legacy
    aud = ROOT/'inputs/audio'
    ai = sorted(aud.glob('ElevenLabs*.mp3'))
    primary = next(p for p in ai if 'shrey' in p.name)
    config = dict(seed=20261022, sample_rate=16000, extended_controls=True,
                  non_speech_duration_sec=20, non_speech_rms_levels=[.003,.03])
    args = SimpleNamespace(ai_audio=primary, extra_ai=[p for p in ai if p != primary],
                           human_audio=sorted(aud.glob('*40s.wav')))
    cases, sources, missing = helper.make_cases(args, config, aud)
    windows=[]; arrays=[]; case_manifest={}; index={}
    for name, c in cases.items():
        pcm = legacy.pcm(c.pop('signal'))
        case_manifest[name] = {**c, 'pcm_sha256':hashlib.sha256(pcm.tobytes()).hexdigest(),
                               'duration_sec':len(pcm)/16000, 'discarded_tail_sec':(len(pcm)%64000)/16000}
        for start in range(0, len(pcm)-64000+1, 64000):
            end=start+64000; a=pcm[start:end].astype(np.float32)/32768
            labels=[l['label'] for l in c['labels'] if l['start'] < end/16000-1e-8 and l['end'] > start/16000+1e-8]
            label=labels[0] if len(set(labels))==1 else 'mixed'
            norm=((a-a.mean())/(a.std()+1e-7)).astype(np.float32)
            digest=hashlib.sha256(norm.tobytes()).hexdigest()
            if digest not in index: index[digest]=len(arrays); arrays.append(norm)
            windows.append(dict(case=name, condition=c['condition'], source_groups=';'.join(c['source_groups']),
                start_sec=start/16000, end_sec=end/16000, label=label,
                scope='transition_diagnostic' if c['condition']=='constructed_transition' else
                      ('non_speech_control' if label in ('non_speech','silence') else 'speech'),
                rms=float(np.sqrt(np.mean(a*a))), input_sha256=digest, array_index=index[digest]))
    np.save(ROOT/'inputs/windows.npy', np.stack(arrays))
    dump(ROOT/'inputs/window_manifest.json', windows)
    dump(ROOT/'inputs/case_manifest.json', case_manifest)
    dump(ROOT/'inputs/source_manifest.json',dict(sources=sources,missing=missing,configuration=config))
    print(f'PREPARED {len(cases)} cases; {len(windows)} windows; {len(arrays)} unique inputs',flush=True)
    return windows, arrays

def run(device):
    import torch
    from transformers import Wav2Vec2Config
    t0=time.perf_counter()
    if (ROOT/'results/v3_logits.json').exists(): raise RuntimeError('Completed run exists; use --summarize')
    specs={'v2':('best.pt','ae78eb6ed8e343dedd72351d942a27718eced82f355a90ef7583334a203beec0'),
           'v3':('detector_state.pt','c634c95b2bb0fb5f5505d4d0364ad96980aa00de83d93bcc04a34ec4585e96a8')}
    versions={}
    for version,(filename,expected) in specs.items():
        folder=ROOT/'inputs/models'/version
        actual=sha(folder/filename)
        if actual!=expected: raise RuntimeError(version+' checkpoint hash mismatch')
        meta=json.loads((folder/'detector_config.json').read_text())
        versions[version]=dict(checkpoint_sha256=actual,config_sha256=sha(folder/'detector_config.json'),
                               config=meta,logit_thresholds=thresholds(meta))
    if versions['v3']['config']['posttrain']['init_checkpoint_sha256'] != versions['v2']['checkpoint_sha256']:
        raise RuntimeError('V3 starting checkpoint does not match V2')
    if sha(ROOT/'inputs/models/v3/detector_config.json')!='23959004a38b64ad387a59f12b4b8b058771f113107cc8c6b9808cb02dc0e9f4':
        raise RuntimeError('V3 config checksum mismatch')
    windows, arrays=prepare()
    arrays=np.stack(arrays)
    torch.manual_seed(20261023); torch.set_num_threads(6)
    if device=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
    metadata=dict(created_local_date='2026-10-23',kind='paired related-source model-only development benchmark',
        device=device,precision='float32; no autocast',python=sys.version,platform=platform.platform(),
        torch=torch.__version__,numpy=np.__version__,versions=versions,
        architecture_sha256=sha(ROOT/'inputs/models/architecture.json'),
        sources_sha256={p.name:sha(p) for p in (ROOT/'sources').glob('*.py')},
        runner_sha256=sha(Path(__file__)),sample_rate=16000,window_sec=4,hop_sec=4,
        preprocessing='mono, polyphase resample to 16 kHz, clip to [-1,1], PCM16 (*32767), /32768, per-window mean/std+1e-7',
        window_count=len(windows),unique_input_count=len(arrays),deduplication='Exact normalized input SHA256; one forward pass per model and unique input',
        inference_scope='Fixed contiguous windows; no speech gate, risk aggregation, call timing, UI or network simulation',
        threshold_policy='Supplied validation thresholds, never selected or adjusted on these test recordings',
        limitations=['Only three ElevenLabs source recordings and two human speakers; derivatives/windows are correlated.',
        'LibriSpeech is in-corpus for V3; supplied config says speakers 1320 and 6930 excluded, not independently audited.',
        'ElevenLabs training overlap unknown; these are reused development recordings.',
        'Noise/music/DTMF are synthetic controls; no real background chatter, own human recordings or live calls supplied.',
        'Only complete four-second windows are scored; tails, mixed windows and inserted silence excluded from speech accuracy.'])
    dump(ROOT/'results/metadata.json',metadata)
    (ROOT/'logs/dependencies.lock.txt').write_text(subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True))
    inference=module('pinned_inference',ROOT/'sources/inference.py')
    original=Wav2Vec2Config.from_pretrained
    Wav2Vec2Config.from_pretrained=classmethod(lambda cls,*a,**kw:Wav2Vec2Config.from_json_file(str(ROOT/'inputs/models/architecture.json')))
    try: model=inference.DeepfakeDetector(versions['v2']['config']['base_model'],12)
    finally: Wav2Vec2Config.from_pretrained=original
    for version,(filename,_) in specs.items():
        print('LOADING',version,flush=True)
        model.to('cpu')
        state=torch.load(ROOT/'inputs/models'/version/filename,map_location='cpu',weights_only=True)
        if 'model' in state: state=state['model']
        model.load_state_dict(state,strict=True); del state; gc.collect()
        model.to(device).eval()
        def sync():
            if device=='mps': torch.mps.synchronize()
        with torch.inference_mode():
            model(torch.from_numpy(arrays[:1]).to(device)); sync()
            logits=[];latencies=[]
            for i in range(len(arrays)):
                sync(); started=time.perf_counter()
                z=float(model(torch.from_numpy(arrays[i:i+1]).to(device)).cpu().item());sync()
                latency=(time.perf_counter()-started)*1000
                if not math.isfinite(z): raise RuntimeError('Nonfinite logit')
                logits.append(z);latencies.append(latency)
                if (i+1)%25==0 or i+1==len(arrays):
                    print(f'{version} {i+1}/{len(arrays)}; last logit {z:.4f}; {latency:.0f} ms',flush=True)
                    dump(ROOT/f'results/{version}_progress.json',dict(completed=len(logits),total=len(arrays)))
            dump(ROOT/f'results/{version}_logits.json',dict(logits=logits,inference_ms=latencies))
    metadata['wall_sec']=time.perf_counter()-t0;dump(ROOT/'results/metadata.json',metadata)
    helper=module('verify_source',ROOT/'sources/run.py');helper.EVAL=EVAL;helper.HERE=EVAL/'benchmark';helper.verify_baseline()
    summarize()

def stats(rows, version, threshold):
    data=[r for r in rows if r['label'] in ('ai','human')]
    ai=[r for r in data if r['label']=='ai'];human=[r for r in data if r['label']=='human']
    tp=sum(r[version+'_logit']>=threshold for r in ai);fp=sum(r[version+'_logit']>=threshold for r in human)
    tn=len(human)-fp;fn=len(ai)-tp
    sens=tp/len(ai) if ai else None;spec=tn/len(human) if human else None
    auc=eer=None
    if ai and human:
        from scipy.stats import rankdata
        z=np.array([r[version+'_logit'] for r in data]); y=np.array([r['label']=='ai' for r in data])
        auc=float((rankdata(z)[y].sum()-len(ai)*(len(ai)+1)/2)/(len(ai)*len(human)))
        # Empirical ROC diagnostic, no test-derived threshold is used for decisions.
        order=np.argsort(-z,kind='stable');zs=z[order];ys=y[order]
        ends=np.r_[np.flatnonzero(np.diff(zs)),len(zs)-1]
        tpr=np.r_[0,np.cumsum(ys)[ends]/len(ai)];fpr=np.r_[0,np.cumsum(~ys)[ends]/len(human)]
        j=int(np.argmin(np.abs(1-tpr-fpr)));eer=float((1-tpr[j]+fpr[j])/2)
    return dict(windows=len(data),ai_windows=len(ai),human_windows=len(human),tp=tp,fn=fn,tn=tn,fp=fp,
        accuracy=(tp+tn)/len(data) if data else None,ai_detection=sens,human_false_positive=1-spec if spec is not None else None,
        balanced_accuracy=(sens+spec)/2 if sens is not None and spec is not None else None,auc=auc,eer=eer)

def summarize():
    meta=json.loads((ROOT/'results/metadata.json').read_text())
    rows=json.loads((ROOT/'inputs/window_manifest.json').read_text())
    preds={v:json.loads((ROOT/f'results/{v}_logits.json').read_text()) for v in ('v2','v3')}
    for r in rows:
        for v in preds:
            z=preds[v]['logits'][r['array_index']];r[v+'_logit']=z
            r[v+'_p_fake']=float(1/(1+np.exp(-z)))
            for op,t in meta['versions'][v]['logit_thresholds'].items():r[v+'_'+op+'_ai']=z>=t
    csvwrite(ROOT/'results/per_window.csv',rows)
    speech=[r for r in rows if r['scope']=='speech' and r['label'] in ('ai','human')]
    clean=[r for r in speech if r['condition']=='original']
    summary=[]
    groups={'all_speech_conditions':speech,'original_only':clean}
    groups.update({c:[r for r in speech if r['condition']==c] for c in sorted({r['condition'] for r in speech}) if c!='original'})
    for group,data in groups.items():
        for version in preds:
            for op,t in meta['versions'][version]['logit_thresholds'].items():
                summary.append(dict(group=group,version=version,operating_point=op,logit_threshold=t,**stats(data,version,t)))
    csvwrite(ROOT/'results/summary.csv',summary);dump(ROOT/'results/summary.json',summary)
    crossover=[]
    for version in preds:
        for threshold_from in preds:
            for op,t in meta['versions'][threshold_from]['logit_thresholds'].items():
                crossover.append(dict(model=version,threshold_from=threshold_from,operating_point=op,**stats(speech,version,t)))
    csvwrite(ROOT/'results/threshold_crossover.csv',crossover)
    case_rows=[]
    for name in dict.fromkeys(r['case'] for r in rows):
        data=[r for r in rows if r['case']==name]
        for version in preds:
            case_rows.append(dict(case=name,version=version,condition=data[0]['condition'],source_groups=data[0]['source_groups'],
                scope=data[0]['scope'],median_logit=float(np.median([r[version+'_logit'] for r in data])),
                **stats([r for r in data if r['scope']=='speech'],version,meta['versions'][version]['logit_thresholds']['threshold_eer'])))
    csvwrite(ROOT/'results/per_case.csv',case_rows)
    controls=[]
    for version in preds:
        for name in dict.fromkeys(r['case'] for r in rows if r['scope']=='non_speech_control'):
            data=[r for r in rows if r['case']==name and r['scope']=='non_speech_control']
            controls.append(dict(case=name,version=version,windows=len(data),median_logit=float(np.median([r[version+'_logit'] for r in data])),
                flagged_eer=sum(r[version+'_threshold_eer_ai'] for r in data),flagged_1pct=sum(r[version+'_threshold_1pct_fpr_ai'] for r in data)))
    csvwrite(ROOT/'results/non_speech_controls.csv',controls)
    def pct(x):return '—' if x is None else f'{x*100:.1f}%'
    def get(group,v,op='threshold_eer'):return next(r for r in summary if r['group']==group and r['version']==v and r['operating_point']==op)
    lines=['# Compare V2 and V3 — October 23, 2026','',
        'Paired local inference on three previously used ElevenLabs recordings (Shrey, Keshav, Azim), two 40-second LibriSpeech human controls, and the previous deterministic distortions and diagnostics.','',
        f"Scored {meta['window_count']} complete windows across {len(case_rows)//2} cases, with {meta['unique_input_count']} unique normalized inputs per model. Primary speech metrics use {len(speech)} windows ({len(clean)} original-bandwidth windows). Repeated inputs were scored once per model and mapped back to every occurrence.",'',
        '| Speech subset / operating point | Model | Accuracy | Balanced accuracy | AI detected | Human false positives | AUC | EER |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for group in ('original_only','all_speech_conditions'):
        for op in ('threshold_eer','threshold_1pct_fpr'):
            for v in preds:
                r=get(group,v,op);lines.append(f"| {group} / {op} | {v.upper()} | {pct(r['accuracy'])} | {pct(r['balanced_accuracy'])} | {pct(r['ai_detection'])} | {pct(r['human_false_positive'])} | {r['auc']:.4f} | {pct(r['eer'])} |")
    lines+=['','The `1pct_fpr` name describes the supplied training-validation operating point; it does not guarantee 1% false positives on these recordings. AUC and EER describe ranking on this reused set; EER is diagnostic only, with no resulting threshold adopted.','',
        '## By audio condition (supplied EER thresholds)','',
        '| Condition | AI / human windows | V2 balanced accuracy | V3 balanced accuracy | V2 human FP | V3 human FP | V2 AI detection | V3 AI detection |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for group in groups:
        if group=='all_speech_conditions':continue
        a,b=get(group,'v2'),get(group,'v3')
        lines.append(f"| {group} | {a['ai_windows']} / {a['human_windows']} | {pct(a['balanced_accuracy'])} | {pct(b['balanced_accuracy'])} | {pct(a['human_false_positive'])} | {pct(b['human_false_positive'])} | {pct(a['ai_detection'])} | {pct(b['ai_detection'])} |")
    lines+=['','## Original recordings','',
        '| Recording | Model | AI / human windows | Median raw logit | Correct at EER threshold |','|---|---|---:|---:|---:|']
    for r in case_rows:
        if r['condition']=='original' and r['scope']=='speech':
            lines.append(f"| {r['source_groups'].replace('supplemental_ai_ElevenLabs_','')} | {r['version'].upper()} | {r['ai_windows']} / {r['human_windows']} | {r['median_logit']:.3f} | {r['tp']+r['tn']} / {r['windows']} |")
    lines+=['','## Interpretation and limits','',
        'The primary comparison changes both model weights and their supplied validation thresholds. `threshold_crossover.csv` also evaluates both models under both threshold sets to expose this interaction. Comparing the old and new training reports directly would mix different validation populations and conditions.','',
        *[f'- {s}' for s in meta['limitations']],
        '- Scores are uncalibrated. A lower AI score by itself is not proof of better accuracy; both AI detection and human false positives are reported.',
        '- Fixed-window transition diagnostics, mixed-boundary windows, inserted silence, and synthetic non-speech probes are retained separately and are not independent speech examples. No call-state or live-call performance claim is made.',
        '- No population confidence interval or significance claim is justified by five source recordings. More real human recordings from outside the training corpora are needed to assess generalization.','',
        '## Reproduction','',f"Device: {meta['device']}; float32; PyTorch {meta['torch']}. Single-window GPU timings include synchronization and host transfer; they exclude warm-up and are not live-call latency.",'',
        'Inputs, checkpoint/config checksums, architecture, source snapshots, normalized windows and exact window hashes are saved under `inputs/` and `sources/`. Per-window logits, summaries, threshold crossover and separate non-speech probes are under `results/`. Dependencies and progress logs are under `logs/`. Frozen earlier benchmark files were verified before and after inference.','']
    (ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    plot(summary)
    print('REPORT SAVED',ROOT/'REPORT.md',flush=True)

def plot(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors=['#6b7280','#087e8b'];fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,(key,title) in zip(axes,[('balanced_accuracy','Balanced accuracy'),('ai_detection','AI detection'),('human_false_positive','Human false positives ↓')]):
        x=np.arange(2)
        for i,v in enumerate(('v2','v3')):
            vals=[next(r[key] for r in summary if r['group']==g and r['version']==v and r['operating_point']=='threshold_eer')*100 for g in ('original_only','all_speech_conditions')]
            bars=ax.bar(x+(i-.5)*.34,vals,.34,label=v.upper(),color=colors[i]);ax.bar_label(bars,fmt='%.1f%%',fontsize=9,padding=3)
        ax.set_xticks(x,['Original audio','All speech conditions']);ax.set_title(title);ax.set_ylim(0,112);ax.set_ylabel('%');ax.spines[['top','right']].set_visible(False)
    axes[0].legend();fig.suptitle('V2 vs V3 • Same audio windows • Supplied EER thresholds',fontweight='bold')
    fig.text(.5,.015,'3 ElevenLabs recordings + 2 human controls; related development data, not population accuracy',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,.94));fig.savefig(ROOT/'results/comparison.png',dpi=180);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--device',default='mps',choices=['mps','cpu']);p.add_argument('--summarize',action='store_true');a=p.parse_args()
    if a.summarize:summarize()
    else:run(a.device)
