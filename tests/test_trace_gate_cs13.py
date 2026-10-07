from cyberscientist import trace_gate


def test_pairing_duplicates_and_timestamp_facts_do_not_claim_platform_score():
    rows = [{'step_type':'tool_call','tool_call_id':'a','timestamp':'2026-10-08T00:00:01Z'},
            {'step_type':'tool_result','tool_call_id':'b','timestamp':'2026-10-08T00:00:00Z'}]
    rows.append(dict(rows[0]))
    result = trace_gate.report(rows, {'solution.py':b'print(42)'}, {'check_items':[]})
    items = {r['code'][:3]:r for r in result['checks']}
    assert items['N08']['evidence']['missing_result_count']==2
    assert items['N08']['evidence']['missing_call_count']==1
    assert items['N12']['evidence']['exact_duplicate_rows']==1
    assert items['N15']['evidence']['nonmonotonic']==1
    assert items['N17']['status']=='unknown' and items['N18']['evidence']['successful_calculation_count'] is None
    assert result['score_prediction'] is None and result['possible_cap'] is None
    assert result['conclusion']=='unknown'


def test_calibrated_n11_risk_affects_only_advisory_conclusion():
    result=trace_gate.report([{'step_type':'observation','body':'fixture'}],{'result.csv':b'42'}, {'check_items':[{'code':'N11_OUTPUT_NOT_CAUSALLY_SUPPORTED','status':'triggered'}]})
    assert result['conclusion']=='risk'
    assert result['calibration']['observations']==1097
    assert result['judge_replica_hint']['enabled'] is False
    assert {x['id'] for x in result['missing_evidence']} >= {'C04','C10'}
