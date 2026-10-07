import copy

from .semantic_projection import project
from .semantics import KEYS


def test_projection_preserves_frozen_original_and_marks_self_report():
    record={'extraction':{k:[] for k in KEYS}}
    record['extraction']['verification']=[{'text':'Executed a check','steps':1,'confidence':.9,
      'evidence':[{'step':1,'quote':'I will check'}]}]
    original=copy.deepcopy(record)
    rows,validation=project(record,[{'index':1,'type':'thought','body':'I will check'}])
    assert record==original and validation['invalid_claims']==0
    assert rows[0]['evidence_source_types']==['assistant_statement']
    assert rows[0]['scientific_truth_status']=='not_independently_verified'
    assert rows[0]['execution_observability']=='unknown_no_visible_tool_result_referenced'
