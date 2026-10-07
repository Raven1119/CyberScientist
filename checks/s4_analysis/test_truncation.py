from .truncation_check import locate


def test_quote_beyond_cut_has_exact_utf16_source_offset_and_exposure_unknown():
    text='😀'+'a'*900+'proof-receipt'
    source=[{'index':1,'body':text}]
    packet={'normalized_events':[{'index':1,'one_line_text':text}]}
    result=locate('proof-receipt',1,source,packet)
    assert result['original_field_offsets'][0]['utf16_offset']==902
    match=result['v6_matches'][0]
    assert match['beyond_900'] and match['beyond_actual_v6_cut']
    assert match['event_selected_in_judge_excerpt'] is None


def test_invented_quote_and_invalid_step_do_not_become_evidence():
    source=[{'index':1,'body':'actual observation'}]
    assert locate('invented',1,source,{}) is None
    assert locate('actual',True,source,{}) is None


def test_short_event_and_v6_code_omission_remain_distinct():
    source=[{'index':1,'code':'verify_output()','body':'running program'}]
    packet={'normalized_events':[{'index':1,'one_line_text':'running program'}]}
    result=locate('verify_output()',1,source,packet)
    assert result['original_field_offsets'][0]['field']=='.code'
    assert not result['v6_matches'] and result['v6_match_status']=='not_located_in_v6_text_or_mapping_unknown'


def setup_input(root):
    from .common import atomic,zstd,write_json
    import json
    atomic(root/'data/traces/1.jsonl.zst',zstd((json.dumps({'type':'message','item':{'text':'observed receipt'}})+'\n').encode()))
    write_json(root/'data/topics/t.json',{'title':'test'})
    return [{'attempt_id':'1','challenge_id':'t','ours':'false','evidence_index':'0','text':'receipt unavailable'}]


def test_native_content_and_packet_changes_invalidate_offsets_without_new_model_calls(tmp_path,monkeypatch):
    import json
    from . import truncation_check as module
    from .common import write_json,atomic,zstd
    items=setup_input(tmp_path);calls=[]
    class Fake:
        def generate(self,system,prompt,**kwargs):
            calls.append(prompt)
            assert 'observed receipt' in prompt
            return {'output':{'checks':[{'id':'0','status':'present','confidence':1,'evidence':[{'step':1,'quote':'observed receipt'}]}]}}
    monkeypatch.setattr(module,'ModelClient',Fake)
    first=module.process(tmp_path,'1',items)
    write_json(tmp_path/'.raw/v6_reports/1.json',{'normalized_events':[{'index':4,'one_line_text':'x'*1000+'observed receipt'}]})
    second=module.process(tmp_path,'1',items)
    assert first['input_fingerprint']!=second['input_fingerprint'] and len(calls)==1
    assert second['checks'][0]['evidence'][0]['v6_matches'][0]['beyond_900']
    atomic(tmp_path/'.raw/bundle_selected_traces/1.jsonl.zst',zstd((json.dumps({'content':'observed receipt'})+'\n').encode()))
    third=module.process(tmp_path,'1',items)
    assert third['trace_source']=='local_only_archive_selected_trace' and len(calls)==2
    assert len(list((tmp_path/'.raw/truncation_history/1').glob('*.json')))==2


def test_duplicate_one_chunk_and_missing_another_cannot_claim_complete_absence(tmp_path,monkeypatch):
    from . import truncation_check as module
    items=setup_input(tmp_path);responses=iter([
        {'checks':[{'id':'0','status':'not_observed','confidence':1}]*2}, {'checks':[]}])
    class Fake:
        def generate(self,*args,**kwargs):return {'output':next(responses)}
    monkeypatch.setattr(module,'ModelClient',Fake)
    monkeypatch.setattr(module,'chunks',lambda events:[events,events])
    result=module.process(tmp_path,'1',items)
    assert result['checks'][0]['status']=='unknown_incomplete_chunks'
