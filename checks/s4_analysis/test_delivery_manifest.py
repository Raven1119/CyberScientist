import json

from .delivery_manifest import analysis_coverage
from .tables import write_csv


def test_delivery_denominator_keeps_uncollected_and_empty_unknowns(tmp_path):
    write_csv(tmp_path/'data/selected.csv',[{'attempt_id':'1','challenge_id':'x','ours':True,'semantic_required':True},
      {'attempt_id':'2','challenge_id':'x','ours':False,'semantic_required':False}])
    write_csv(tmp_path/'data/trace_features.csv',[],fields=['attempt_id','public_trace_status'])
    write_csv(tmp_path/'data/missing_evidence.csv',[{'attempt_id':'1','text':'check'}])
    directory=tmp_path/'data/truncation_claims';directory.mkdir()
    (directory/'1.json').write_text(json.dumps({'checks':[{'status':'unknown_public_trace_empty'}]}))
    summary=analysis_coverage(tmp_path)
    assert summary['selected_attempts']==2 and summary['trace_retrieved']==0
    assert summary['semantic_statuses']=={'unknown_no_extraction':1}
    import csv
    rows=list(csv.DictReader((tmp_path/'data/analysis_coverage.csv').open()))
    assert rows[0]['truncation_assessed_checks']=='0' and rows[0]['ours']=='True'
