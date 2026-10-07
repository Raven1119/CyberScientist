from .comparisons import jaccard,package_name,reliability


def test_unknown_hashes_and_standard_library_do_not_become_environment_gaps():
    assert jaccard([],['a']) is None and jaccard(['a'],['a','b'])==.5
    assert package_name('json') is None and package_name('os.path') is None
    assert package_name('sklearn.cluster')=='scikit-learn'


def test_reliability_requires_positive_sample_floor_and_both_rates():
    assert reliability(2,0,0,2)==(1,1,'unknown_or_unusable')
    assert reliability(5,0,0,5)==(1,1,'conditionally_reliable')
    assert reliability(9,1,4,13)[2]=='unknown_or_unusable'
    assert reliability(0,0,0,0)==(None,None,'unknown_or_unusable')


def test_report_snapshot_excludes_stale_unselected_and_ignores_later_write(tmp_path):
    import json
    from .comparisons import selected_reports
    directory=tmp_path/'.raw/v6_reports';directory.mkdir(parents=True)
    path=directory/'1.json';path.write_text(json.dumps({'status':'unknown_public_trace_empty'}))
    (directory/'99.json').write_text(json.dumps({'status':'ok','cap':100}))
    frozen=selected_reports(tmp_path,['1','2'])
    path.write_text(json.dumps({'status':'ok','cap':100}))
    assert set(frozen)=={'1','2'} and frozen['1']['report']['status']=='unknown_public_trace_empty'
    assert frozen['2']['report']=={} and frozen['2']['sha256'] is None


def test_environment_head_uses_full_details_without_rewriting_frozen_selection(tmp_path):
    from .comparisons import current_head_rows
    from .tables import write_csv
    from .common import sha
    base={'challenge_id':'topic','author_id':'author','ours':False,'created_at':'2026-01-01T00:00:00Z'}
    write_csv(tmp_path/'data/selected.csv',[{**base,'attempt_id':'1','display_score':40,'head_rank':1}])
    frozen=sha((tmp_path/'data/selected.csv').read_bytes())
    write_csv(tmp_path/'data/attempts.csv',[{**base,'attempt_id':'1','display_score':40},{**base,'attempt_id':'2','display_score':90}])
    assert [r['attempt_id'] for r in current_head_rows(tmp_path)]==['2']
    assert sha((tmp_path/'data/selected.csv').read_bytes())==frozen
