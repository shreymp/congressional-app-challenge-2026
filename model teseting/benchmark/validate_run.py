"""Auditable invariants for one saved real-model replay (no inference rerun)."""
import argparse,importlib.util,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('benchmark_run',HERE/'run.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)


def validate(path):
    report=json.loads((path/'results.json').read_text());frozen=json.loads((bench.EVAL/'results/real_audio_results.json').read_text());checks=[]
    def check(name,passed,detail=None):checks.append(dict(name=name,passed=bool(passed),detail=detail))
    check('frozen_artifacts_unchanged',bool(bench.verify_baseline()))
    check('all_18_named_regressions_present',all(n in report['cases'] for n in frozen['cases']))
    check('frozen_inputs_logits_completion_reproduced',report['frozen_reproduction']['passed'])
    if report['metadata'].get('benchmark_runner_sha256'):
        check('saved_runner_hash_matches_metadata',bench.sha(path/'runner.py')==report['metadata']['benchmark_runner_sha256'])
    for rel,expected in report['metadata']['source_hashes']['candidate'].items():
        check('frozen_candidate_source:'+rel,bench.sha(path/'sources/candidate'/rel)==expected)
    check('dependency_lock_hash',bench.sha(path/'dependencies.lock.txt')==report['metadata']['dependency_lock_sha256'])
    for name,case in report['cases'].items():
        check(name+':source_group_retained',bool(case['source_groups']))
        for selection,data in case['selections'].items():
            for w in data['windows']:
                check(f'{name}/{selection}/{w["window_id"]}:source_interval_bounds',all(0<=s<e<=data['duration_sec']+1e-8 for s,e in w['audio_intervals']))
                check(f'{name}/{selection}/{w["window_id"]}:call_end_cancellation',w.get('completed_at',data['duration_sec']+1)>data['duration_sec'] if not w['completed'] and w['completion_reason']=='cancelled_at_call_end' else not w['completed'] or w['completed_at']<=data['duration_sec'])
        for key,e in case['experiments'].items():
            check(name+'/'+key+':no_human_warning_contradiction',e['metrics']['human_with_warning_sec']==0)
            check(name+'/'+key+':all_submissions_accounted',e['metrics']['submitted_count']==e['metrics']['completed_count']+e['metrics']['cancelled_or_rejected_completion_count'])
        if name in frozen['cases']:
            for kind in ('baseline','current'):
                ref=frozen['cases'][name]['production'][kind]['summary'];tl=case['experiments'][kind+'__'+kind]['timeline']
                for state in ('ai','human'):
                    actual=next((r['t'] for r in tl if r['state']==state),None);expected=ref['first_'+state]
                    check(f'{name}/{kind}:backend_first_{state}_reproduced',(actual is None and expected is None) or (actual is not None and expected is not None and abs(actual-expected)<=.1),dict(expected=expected,actual=actual))
                check(f'{name}/{kind}:backend_final_reproduced',tl[-1]['state']==ref['final']['state'])
    result=dict(passed=all(c['passed'] for c in checks),check_count=len(checks),failed=[c for c in checks if not c['passed']],checks=checks)
    bench.dump(path/'invariants.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2))
    return result['passed']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);raise SystemExit(0 if validate(parser.parse_args().run) else 1)
