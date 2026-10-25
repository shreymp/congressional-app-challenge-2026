"""Check input integrity, metric arithmetic, and CPU/GPU agreement independently."""
import csv, hashlib, importlib.util, json, math, sys
from pathlib import Path
import numpy as np
import torch
from transformers import Wav2Vec2Config
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads((ROOT/p).read_text())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
meta=read('results/metadata.json');manifest=read('inputs/window_manifest.json')
W=np.load(ROOT/'inputs/windows.npy',mmap_mode='r')
assert W.shape==(meta['unique_input_count'],64000)
assert np.isfinite(W).all()
hashes=[hashlib.sha256(x.tobytes()).hexdigest() for x in W]
assert all(hashes[r['array_index']]==r['input_sha256'] for r in manifest)
assert len(manifest)==meta['window_count']
assert sha(ROOT/'compare.py')==meta['runner_sha256']
assert all(sha(ROOT/'sources'/name)==digest for name,digest in meta['sources_sha256'].items())
source=read('inputs/source_manifest.json')
assert all(sha(s['path'])==s['sha256'] for s in source['sources'].values())
for v,filename in [('v2','best.pt'),('v3','detector_state.pt')]:
    assert sha(ROOT/'inputs/models'/v/filename)==meta['versions'][v]['checkpoint_sha256']
pred={v:read(f'results/{v}_logits.json')['logits'] for v in ('v2','v3')}
assert all(len(z)==len(W) and np.isfinite(z).all() for z in pred.values())
summary=read('results/summary.json')
checks=[]
for row in summary:
    group=row['group'];v=row['version'];t=row['logit_threshold']
    selected=[r for r in manifest if r['scope']=='speech' and r['label'] in ('ai','human') and
              (group=='all_speech_conditions' or r['condition']==('original' if group=='original_only' else group))]
    ai=np.array([pred[v][r['array_index']] for r in selected if r['label']=='ai'])
    human=np.array([pred[v][r['array_index']] for r in selected if r['label']=='human'])
    tp=int(np.sum(ai>=t));fp=int(np.sum(human>=t))
    assert (tp,fp,len(ai),len(human))==(row['tp'],row['fp'],row['ai_windows'],row['human_windows'])
    assert abs(row['accuracy']-(tp+len(human)-fp)/len(selected))<1e-12
    if len(ai) and len(human):
        auc=float(((ai[:,None]>human).sum()+.5*(ai[:,None]==human).sum())/(len(ai)*len(human)))
        assert abs(auc-row['auc'])<1e-12
    checks.append(dict(group=group,version=v,operating_point=row['operating_point'],passed=True))
# Deliberately chosen before checking CPU outputs: each source class and regressions.
samples=[]
for case in ['original','librispeech_test_clean_1320_40s','librispeech_test_clean_6930_40s',
             'white_noise_10dB_SNR','control_dtmf_rms0.03','control_silence']:
    r=next(r for r in manifest if r['case']==case)
    samples.append((case,r['array_index']))
inference=load('pinned_inference',ROOT/'sources/inference.py')
original=Wav2Vec2Config.from_pretrained
Wav2Vec2Config.from_pretrained=classmethod(lambda cls,*a,**kw:Wav2Vec2Config.from_json_file(str(ROOT/'inputs/models/architecture.json')))
try:model=inference.DeepfakeDetector(meta['versions']['v2']['config']['base_model'],12)
finally:Wav2Vec2Config.from_pretrained=original
torch.set_num_threads(6);numeric=[]
for v,filename in [('v2','best.pt'),('v3','detector_state.pt')]:
    state=torch.load(ROOT/'inputs/models'/v/filename,map_location='cpu',weights_only=True)
    model.load_state_dict(state['model'] if 'model' in state else state,strict=True);del state
    model.eval()
    with torch.inference_mode():
        for case,i in samples:
            z=float(model(torch.from_numpy(W[i:i+1].copy())).item());gpu=pred[v][i];err=abs(z-gpu)
            assert err<=.01,(v,case,z,gpu,err)
            numeric.append(dict(version=v,case=case,cpu_logit=z,gpu_logit=gpu,abs_error=err,passed=True))
helper=load('benchmark_snapshot',ROOT/'sources/run.py');helper.EVAL=ROOT.parent;helper.HERE=ROOT.parent/'benchmark';helper.verify_baseline()
result=dict(passed=True,input_windows_checked=len(manifest),unique_hashes_checked=len(W),
    metric_rows_checked=len(checks),independent_auc='All pairwise AI/human comparisons with half-credit for ties',
    cpu_gpu_logit_tolerance=.01,numeric_checks=numeric,frozen_previous_baseline_unchanged=True)
(ROOT/'results/validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
