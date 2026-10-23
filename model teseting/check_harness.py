"""Meaningful harness integrity checks; no model accuracy claims."""
import io,json,sys,hashlib
from pathlib import Path
import numpy as np,soundfile as sf
R=Path(__file__).resolve().parent
# All 256 G.711 codewords: libsndfile reference decoder versus original detector's decoder.
sys.path.insert(0,str(R/'snapshots/current/model'))
from inference import Detector
codes=bytes(range(256));b=io.BytesIO(codes)
y,s=sf.read(b,samplerate=8000,channels=1,format='RAW',subtype='ULAW',dtype='float32')
assert np.array_equal(y,Detector.mulaw_bytes_to_float(codes))
b=io.BytesIO();sf.write(b,np.array([0,32767,-32768],np.int16),8000,format='RAW',subtype='ULAW')
assert b.getvalue()==bytes([255,128,0]),b.getvalue()
r=json.loads((R/'results/real_audio_results.json').read_text());counts=[]
for name,c in r['cases'].items():
 for v,prod in c['production'].items():
  for w in prod['windows']:
   intervals=w['audio_intervals'];total=sum(round((e-s)*16000) for s,e in intervals)
   assert total==w['input_samples'],(name,v,total,w['input_samples'])
   assert all(0<=s<e<=w['submitted_at']+1e-6 for s,e in intervals)
   if w['completed']:assert abs(w['completed_at']-w['submitted_at']-w['infer_ms']/1000)<1e-5
   assert not w['cache_reused']
  assert all(a['t']<=b['t'] for a,b in zip(prod['timeline'],prod['timeline'][1:]))
 for v in ['baseline','current']:
  got=c['matched'][v]['windows'];expected=[w for w in c['production']['current']['windows'] if w['completed']]
  assert got==expected,(name,v,'matched inputs differ')
 for lab in c['labels']:
  assert lab['end']<=c['production']['current']['summary']['duration_sec']+1e-6
 counts.append({'case':name,'production_submissions':sum(len(p['windows']) for p in c['production'].values())})
assert sum(x['production_submissions'] for x in counts)==r['actual_model_inferences']
print(json.dumps({'passed':['all_256_G711_codewords_match_original_decoder','G711_encoder_golden_vectors','all_submitted_intervals_cover_exact_input','completion_times_match_measured_latency','all_production_submissions_executed_model','matched_aggregation_inputs_identical','timeline_monotonic_and_label_bounds'],'case_counts':counts},indent=2))
