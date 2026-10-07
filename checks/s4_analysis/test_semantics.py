from .semantics import KEYS,chunks,validate


def test_large_event_segmentation_preserves_every_serialized_character():
    import json
    event={'index':1,'body':'abc'*1000}
    actual=chunks([event],limit=200)
    assert ''.join(c[0]['serialized_step_fragment'] for c in actual)==json.dumps(event,ensure_ascii=False)
    assert all(c[0]['index']==1 for c in actual)


def test_step_and_quote_format_repairs_do_not_invent_evidence():
    text='original scientific process description '*10
    output={k:[] for k in KEYS}
    output['verification']=[{'text':'The agent described a check.','steps':2,'confidence':.8,
                             'evidence':[{'step':2,'quote':text}]}]
    result=validate(output,[{'index':2,'body':text}])
    assert not result['invalid_claims'] and len(result['lossless_normalizations'])==2
    assert output['verification'][0]['steps']==[2]
    output['verification'][0]['evidence'][0]['quote']='invented result'
    result=validate(output,[{'index':2,'body':text}])
    assert result['invalid_claims']==1 and 'quote_not_exact' in result['issues'][0]['errors']


def test_malformed_quote_shapes_are_invalid_evidence_without_crashing():
    output={k:[] for k in KEYS}
    output['verification']=[{'text':'claim','steps':[1],'confidence':1,
      'evidence':[{'step':[1],'quote':'actual'},'malformed']}]
    result=validate(output,[{'index':1,'body':'actual'}])
    assert result['invalid_claims']==1 and 'invalid_quote_step' in result['issues'][0]['errors']
    assert 'invalid_quote_object' in result['issues'][0]['errors']


def test_quote_spanning_separate_fields_is_not_an_exact_source_substring():
    output={k:[] for k in KEYS}
    output['verification']=[{'text':'claim','steps':[1],'confidence':1,
      'evidence':[{'step':1,'quote':'first\nsecond'}]}]
    result=validate(output,[{'index':1,'body':'first','code':'second'}])
    assert result['invalid_claims']==1 and 'quote_not_exact' in result['issues'][0]['errors']


def test_attribution_keeps_self_report_separate_from_visible_numeric_zero_result():
    output={k:[] for k in KEYS}
    output['verification']=[{'text':'claim','steps':[1],'confidence':1,'evidence':[{'step':1,'quote':'I will check'}]}]
    validate(output,[{'index':1,'type':'thought','body':'I will check'}])
    c=output['verification'][0]
    assert c['evidence_source_types']==['assistant_statement']
    assert c['execution_observability']=='unknown_no_visible_tool_result_referenced'
    c['steps']=[2];c['evidence']=[{'step':2,'quote':'0'}]
    validate(output,[{'index':2,'type':'tool_result','tool_output':0}])
    assert c['evidence_source_types']==['tool_result_with_visible_body']
    assert c['scientific_truth_status']=='not_independently_verified'
