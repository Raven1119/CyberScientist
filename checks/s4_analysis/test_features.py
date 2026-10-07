from .features import NUMBER,extract,offsets,utf16_length


def test_offsets_count_utf16_surrogate_pairs_like_javascript():
    text='😀 value 12.5'
    assert utf16_length(text)==len(text)+1
    assert offsets(NUMBER,text)==[[9,13]]


def test_empty_public_trace_does_not_invent_timing_or_checklist_score(tmp_path):
    feature,events=extract('1',{'challenge_id':'c','ours':True},[],
                            {'status':'unknown_public_trace_empty'},tmp_path)
    assert feature['duration_s'] is None and feature['v6_checklist_score'] is None
    assert feature['public_trace_status']=='empty_unknown_original' and not events


def test_pairing_counts_distinct_valid_ids_and_keeps_output_causality_unknown(tmp_path):
    steps=[{'type':'tool_call','tool_call_id':'a','body':'pip install scipy==1.2'},
           {'type':'tool_call','tool_call_id':'a'}, {'type':'tool_result','tool_call_id':'a'},
           {'type':'tool_call','tool_call_id':True}]
    feature,events=extract('1',{'challenge_id':'c','ours':False},steps,{'status':'failed'},tmp_path)
    assert feature['tool_call_ids']==1 and feature['paired_tool_call_ids']==1
    assert feature['submitted_output_inventory_status']=='unknown_bundle_unavailable'
    assert any(e['event_kind']=='software_install_candidate' for e in events)


def test_nested_command_fields_are_visible_and_missing_ids_are_unknown(tmp_path):
    steps=[{'type':'tool_call','tool_args':{'command':'import pymatgen\nfrom ase import Atoms'}},
           {'type':'tool_result','body':''}]
    feature,events=extract('1',{'challenge_id':'c','ours':False},steps,
       {'normalized_events':[{'index':1,'text':'unrelated sealed event'}]},tmp_path)
    assert 'pymatgen' in feature['imports_json'] and 'ase' in feature['imports_json']
    assert feature['command_sequence_sha256'] and feature['visible_command_steps']==1
    assert feature['pairing_status']=='unknown_missing_ids'
    assert feature['tool_results_with_visible_content']==0
    assert feature['v6_event_alignment_status']=='unknown_different_or_unbound_input'
    assert all(not e['v6_normalized_text_available'] for e in events)


def test_feature_fingerprint_changes_with_trace_or_declared_inventory(tmp_path):
    from .features import input_fingerprint
    from .common import write_json
    item={'challenge_id':'c','ours':False}
    first=input_fingerprint(tmp_path,'1',b'unchanged report',b'old trace',item)
    assert input_fingerprint(tmp_path,'1',b'unchanged report',b'new trace',item)!=first
    write_json(tmp_path/'data/bundle_inventories/1.json',{'files':[]})
    assert input_fingerprint(tmp_path,'1',b'unchanged report',b'old trace',item)!=first


def test_numeric_only_result_is_visible_and_numeric_arguments_affect_hash(tmp_path):
    item={'challenge_id':'c','ours':False}
    a,_=extract('1',item,[{'type':'tool_result','tool_output':{'energy':-1.234}},
                        {'type':'tool_call','tool_args':{'iterations':10}}],{},tmp_path)
    b,_=extract('1',item,[{'type':'tool_result','tool_output':{'energy':-1.234}},
                        {'type':'tool_call','tool_args':{'iterations':11}}],{},tmp_path)
    assert a['tool_results_with_visible_content']==1
    assert a['command_sequence_sha256']!=b['command_sequence_sha256']
