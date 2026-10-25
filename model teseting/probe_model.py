import os,time,json,sys,hashlib
from pathlib import Path
T=time.perf_counter(); ROOT=Path(__file__).resolve().parent
import numpy as np,torch,soundfile as sf
from scipy.signal import resample_poly
from transformers import Wav2Vec2Config
original=Wav2Vec2Config.from_pretrained
Wav2Vec2Config.from_pretrained=classmethod(lambda cls,base,*a,**kw: original(str(ROOT/'snapshots/architecture'),*a,**kw))
sys.path.insert(0,str(ROOT/'snapshots/current/model'))
from inference import Detector
# Stage config + symlink, without changing supplied source.
w=ROOT/'weights';w.mkdir(exist_ok=True)
(w/'detector_config.json').write_bytes((ROOT/'snapshots/current/model/detector_config.json').read_bytes())
if not (w/'best.pt').exists(): (w/'best.pt').symlink_to('/Users/spatel7/Downloads/best.pt')
assert hashlib.file_digest((w/'best.pt').open('rb'),'sha256').hexdigest()=='ae78eb6ed8e343dedd72351d942a27718eced82f355a90ef7583334a203beec0'
a,sr=sf.read('/Users/spatel7/Downloads/ElevenLabs_2026-10-23T01_11_44_shrey_ivc_sp100_s50_sb75_v4.mp3',dtype='float32');a=resample_poly(a,160,441)[:64000];a=(a-a.mean())/(a.std()+1e-7)
out={'imports_sec':time.perf_counter()-T,'mps_available':torch.backends.mps.is_available(),'torch_threads':torch.get_num_threads()}
for dev in ['mps','cpu']:
 try:
  t=time.perf_counter();d=Detector(str(w),device=dev);out[dev]={'load_sec':time.perf_counter()-t,'runs':[]}
  for _ in range(3):
   t=time.perf_counter()
   with torch.no_grad(): z=float(d.model(torch.from_numpy(a)[None].to(dev)).item())
   out[dev]['runs'].append({'logit':z,'sec':time.perf_counter()-t})
  del d
 except Exception as e: out[dev]={'error':repr(e)}
 print(json.dumps(out),flush=True)
(ROOT/'results/model_probe.json').write_text(json.dumps(out,indent=2))
