import io,json,zipfile
from cyberscientist import trace_hints,db,mailboxes,submission_receipts
from test_auto_harvest import seed


def test_hints_only_from_official_trace_and_diagnostic_failure_advisory(monkeypatch):
    result=io.BytesIO()
    with zipfile.ZipFile(result,'w') as archive:
        archive.writestr('arm_manifest.json',json.dumps({'trace':'traces/trace.jsonl'}))
        archive.writestr('traces/trace.jsonl','{"type":"tool_result","body":"observed"}\n')
        archive.writestr('outputs/result.json','{}')
    def evaluate(rows,task,outputs,convert):
        assert rows==[{'type':'tool_result','body':'observed'}] and convert is False
        assert outputs=={'outputs/result.json':b'{}'}
        return {'details':[{'code':'N11_OUTPUT_NOT_CAUSALLY_SUPPORTED','status':'triggered'},{'code':'N01_OTHER','status':'triggered'}],'checklist_score':36}
    monkeypatch.setattr(trace_hints.trace_diagnostics,'_evaluate',evaluate)
    hint=trace_hints.inspect(result.getvalue())
    assert [h['code'] for h in hint['hints']]==['N11_OUTPUT_NOT_CAUSALLY_SUPPORTED']
    assert 'checklist_score' not in hint and 'score' not in hint and hint['advisory_only']
    assert trace_hints.inspect(b'not a zip')['advisory_only']


def test_each_real_code_observation_calibrated_once():
    rid,source=seed(10)
    hint={'status':'ready','hints':[{'code':'N11_OUTPUT_NOT_CAUSALLY_SUPPORTED'}]}
    with db.transaction() as conn:
        row=conn.execute('SELECT * FROM submissions WHERE id=?',(source['id'],)).fetchone()
        mailboxes._record_feedback(conn,row,'trace_hint',hint)
        receipt={'resultsJson':{'trace_low_score_reasons':[{'code':'N11_OUTPUT_NOT_CAUSALLY_SUPPORTED','score_effect':-6}]}}
        submission_receipts.observe_tx(conn,row,receipt)
        submission_receipts.observe_tx(conn,row,receipt)
    assert len(db.query('SELECT * FROM trace_hint_calibrations'))==1
    assert json.loads(db.query_one('SELECT comparison_json FROM trace_hint_calibrations')[0])['matched']==['N11_OUTPUT_NOT_CAUSALLY_SUPPORTED']
