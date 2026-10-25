import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('benchmark_run',Path(__file__).resolve().parents[1]/'run.py')
bench=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    def test_frozen_manifest_unchanged(self):
        self.assertGreater(len(bench.verify_baseline()['sha256']),100)

    def test_decode_uses_actual_rate(self):
        import numpy as np,soundfile as sf
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.wav';sf.write(p,np.ones(24000,dtype=np.float32)*.1,24000)
            signal,meta=bench.decode(p)
            self.assertEqual(meta['decoded_sample_rate'],24000)
            self.assertEqual(len(signal),16000)

    def test_qualified_warning_never_reassures(self):
        row=bench.display(dict(state='human',recent_ai=True),'qualified_recent_warning',10)
        self.assertEqual(row['displayed_state'],'recent_warning')
        row=bench.display(dict(state='ai',recent_ai=True),'qualified_recent_warning',10)
        self.assertEqual(row['displayed_state'],'ai')

    def test_missing_and_rejected_remain_metrics(self):
        rows=[dict(t=t,state='analyzing',displayed_state='uncertain',recent_ai=False) for t in (0,4)]
        source=dict(duration_sec=4,windows=[],attempts=[dict(submitted=False,reason='audio_too_quiet')])
        m=bench.metrics(rows,source,[dict(start=0,end=4,label='ai')])
        self.assertFalse(m['analysis_coverage']);self.assertEqual(m['rejected_attempt_count'],1)
        self.assertIsNone(m['transitions'][0]['target_delay_sec']);self.assertEqual(m['abstention_sec'],4)

    def test_switch_inherits_boundary_state(self):
        rows=[dict(t=t,state='human',displayed_state='human',recent_ai=False) for t in (0,1.02,2)]
        source=dict(duration_sec=2,windows=[],attempts=[])
        m=bench.metrics(rows,source,[dict(start=0,end=1.01,label='ai'),dict(start=1.01,end=2,label='human')])
        self.assertEqual(m['transitions'][1]['target_delay_sec'],0)
        self.assertAlmostEqual(m['incorrect_human_sec'],1.01)

    def test_overlap_old_speech_cannot_count_new_silence(self):
        window=dict(evidence_start_sec=1.,evidence_end_sec=5.,usable_audio_intervals=[[1.,3.]])
        c=bench.fresh_contribution(window,4.)
        self.assertEqual(c['usable_sec'],0.)
        self.assertFalse(c['accepted'])

    def test_overlap_counts_only_tail_speech(self):
        window=dict(evidence_start_sec=1.,evidence_end_sec=5.,usable_audio_intervals=[[1.,3.],[4.5,5.]])
        c=bench.fresh_contribution(window,4.)
        self.assertEqual(c['usable_sec'],.5)
        self.assertEqual(c['weight'],.5)

    def test_call_end_does_not_flush_inference(self):
        import numpy as np
        class D:
            meta=dict(threshold_eer=.99,threshold_1pct_fpr=.999,window_sec=4.)
            def score_window(self,a):return dict(p_fake=.9999,logit=10.,infer_ms=40.)
        c=dict(frame_samples=320,score_interval_sec=1.)
        signal=(np.ones(64000)*1000).astype(np.int16)
        selected=bench.selection(D(),signal,bench.EVAL/'snapshots/current','current',c)
        self.assertEqual(len(selected['windows']),1)
        self.assertFalse(selected['windows'][0]['completed'])
        self.assertEqual(selected['windows'][0]['completion_reason'],'cancelled_at_call_end')


if __name__=='__main__':unittest.main()
