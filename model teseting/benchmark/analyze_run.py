"""Summarize a versioned run without treating related windows as independent calls."""
import argparse,json,statistics
from pathlib import Path


def main(path):
    report=json.loads((path/'results.json').read_text());cases=report['cases']
    lines=['# Development interpretation','','This report contains reused and transformed development sources. No independent accuracy, calibrated probability, live-call latency, or release readiness is established.','','## Coverage and provenance','',f"Cases: {len(cases)}. Actual model inferences: {report['metadata'].get('actual_model_inferences','run incomplete')}. Device: {report['metadata']['device']}.",f"Frozen reproduction: {report.get('frozen_reproduction',{}).get('passed','not yet checked')}.",'','All derived clips retain source groups. The original regressions comprise one AI source and two human source recordings. Supplemental user-supplied ElevenLabs recordings, when present, are development-only same-system sources with unverified identity/consent/training overlap. Transforms and repeated prefixes are not additional independent calls. Synthetic controls have their own explicit groups.','','## Current evidence and eligibility','','| Case | Experiment | Completed | Incorrect Human s | False AI s | False warning s | Switch target delays s | Final |','|---|---|---:|---:|---:|---:|---|---|']
    focus=['original','low_volume_minus20dB','white_noise_10dB_SNR','librispeech_test_clean_1320_40s','librispeech_test_clean_6930_40s','diagnostic_human_prefix120_then_ai','diagnostic_ai_then_human6930']
    for name in focus:
        if name not in cases:continue
        for key in ('current__current','current__candidate_mean','current__candidate_decay','candidate_quiet__candidate_mean','candidate_quiet__candidate_decay','candidate_quiet_overlap1s__candidate_mean','candidate_quiet_overlap2s__candidate_mean'):
            if key not in cases[name]['experiments']:continue
            m=cases[name]['experiments'][key]['metrics'];delays=', '.join(t['label']+': '+('unreached' if t['target_delay_sec'] is None else f"{t['target_delay_sec']:.2f}") for t in m['transitions'])
            lines.append(f"| {name} | {key} | {m['completed_count']} | {m['incorrect_human_sec']:.2f} | {m['false_ai_sec']:.2f} | {m['false_warning_sec']:.2f} | {delays} | {m['final']['displayed_state']} |")
    lines+=['','## Non-speech controls','','| Case | Selection | Submitted/completed | Mean speech estimate weight | Candidate mean confident seconds |','|---|---|---:|---:|---:|']
    for name,c in cases.items():
        if not name.startswith('control_'):continue
        for selection,s in c['selections'].items():
            weights=[w['weight'] for w in s['windows']];key=selection+'__candidate_mean';m=c['experiments'].get(key,{}).get('metrics',{})
            lines.append(f"| {name} | {selection} | {len(weights)}/{sum(w['completed'] for w in s['windows'])} | {statistics.mean(weights) if weights else 0:.3f} | {m.get('non_speech_confident_sec',0):.2f} |")
    lines+=['','## Symmetric degradation logits','','Medians describe correlated windows within a source/condition. They are not speaker-level uncertainty estimates. No threshold is selected from this table.','','| Source/condition | Fixed contiguous median logit | Adaptive median logit |','|---|---:|---:|']
    for name,c in cases.items():
        if 'then_' in name or name.startswith('control_') or name.startswith('pause_'):continue
        med=[]
        for selection in ('current','candidate_quiet'):
            z=[w['logit'] for w in c['selections'].get(selection,{}).get('windows',[]) if w['completed']]
            med.append('unscored' if not z else f'{statistics.median(z):.3f}')
        lines.append(f'| {name} | {med[0]} | {med[1]} |')
    lines+=['','## Release interpretation','','Candidates remain disabled by default. Faster recovery or restored quiet eligibility does not offset a new human false-warning regression without the predeclared independent evaluation. The current shadow warning is not exported as a default legacy alert. Original thresholds and checkpoint are unchanged.','','A missing/rejected sample remains an abstention/coverage outcome; it does not disappear from the denominator. Physical call timing, disclosure delay, app receipt/display, same-speaker provenance, training overlap, real TV/chatter/music controls, and held-out calibration remain unknown. Synthetic logic, real-model replay, independent held-out data and actual live calls are separate evidence categories.','']
    (path/'analysis.md').write_text('\n'.join(lines))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);main(p.parse_args().run)
