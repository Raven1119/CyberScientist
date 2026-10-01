import json

from cyberscientist import db, mailboxes
from test_local_scoring import _scorer
from test_trace_narrative import _fixture, _zip


def test_preflight_exposes_task_and_verified_scorer_paths_before_sealing():
    rid, tid, _, files, _, _, _, _, directory = _fixture()
    db.execute("UPDATE challenges SET content=? WHERE id='MB_CH'",
               ('交付要求：请输出 `answer.txt`。',))
    scorer = _scorer()
    descriptor = json.loads((scorer / 'scorer.json').read_text())
    descriptor['input_contract'] = {
        'artifact_paths': ['outputs/answer.txt'], 'required': True,
        'verification': 'synthetic historical replay'}
    (scorer / 'scorer.json').write_text(json.dumps(descriptor))
    files['answer.txt'] = b'fixture answer\n'
    (directory / 'result_package.zip').write_bytes(_zip(files))
    result = mailboxes.preflight_submission(rid, tid, None)
    contract = result['artifact_contract']
    assert 'answer.txt' in contract['task_paths']
    assert contract['scorer_paths'] == ['outputs/answer.txt']
    assert contract['status'] == 'mismatch'
    assert contract['missing'] == ['outputs/answer.txt']
    assert contract['warnings']
    # Inspection is advisory: the executor chooses its own packaging remedy.
    assert 'outputs/answer.txt' not in files
    files['outputs/answer.txt'] = files['answer.txt']
    (directory / 'result_package.zip').write_bytes(_zip(files))
    repaired = mailboxes.preflight_submission(rid, tid, None)['artifact_contract']
    assert repaired['missing'] == []
    assert repaired['status'] == 'ready'


def test_no_declared_scorer_contract_is_unknown_not_invented():
    rid, tid, *_ = _fixture()
    result = mailboxes.preflight_submission(rid, tid, None)
    assert result['artifact_contract']['status'] == 'unavailable'
    assert result['artifact_contract']['scorer_paths'] == []


async def test_trial_prompt_exposes_contract_and_authorized_sandbox_before_packaging():
    from test_collaboration import _rig, _seed_challenge, _start, _wait
    from cyberscientist import config
    _seed_challenge('MB_CH')
    scorer = _scorer()
    value = json.loads((scorer / 'scorer.json').read_text())
    value['input_contract'] = {'artifact_paths': ['outputs/synthetic.txt'],
                              'required': True, 'verification': 'synthetic verifier replay'}
    (scorer / 'scorer.json').write_text(json.dumps(value))
    db.execute("UPDATE challenges SET content='交付要求：`synthetic.txt`' WHERE id='MB_CH'")
    c, brain, executor = _rig(shadow=False)
    rid = c.create_run('MB_CH')['id']
    await _start(c, brain, rid)
    assert await _wait(lambda: bool(executor.prompts))
    prompt = executor.prompts[0][1]
    assert 'outputs/synthetic.txt' in prompt and 'synthetic.txt' in prompt
    assert 'Bohrium Job 或沙箱' in prompt
    assert '预置环境事实' in prompt
