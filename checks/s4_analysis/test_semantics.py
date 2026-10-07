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
