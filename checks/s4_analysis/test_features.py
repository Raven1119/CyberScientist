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
