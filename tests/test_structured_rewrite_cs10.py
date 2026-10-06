import asyncio
import json
import time
import pytest
from cyberscientist import structured_output
from cyberscientist.brains.base import BrainEvent, SessionRef
from cyberscientist.brains.codex import CodexBrain
from cyberscientist.brains.kimi import KimiBrain
from test_decision import valid_decision


class NativeRPC:
    def __init__(self, texts, kind):
        self.texts, self.kind, self.calls = texts, kind, []
        self.ready = asyncio.Event()
        self.emitted = 0

    async def request(self, method, params, **kwargs):
        self.calls.append((method, params))
        if self.kind == 'codex': return {'turn': {'id': str(len(self.calls))}}
        await self.ready.wait(); self.ready.clear()
        return {'stopReason': 'end_turn'}

    async def notifications(self):
        if self.kind == 'codex':
            text = self.texts[len(self.calls) - 1]
            yield {'method': 'item/completed', 'params': {'threadId': 'same-session', 'item': {'type': 'agentMessage', 'text': text}}}
            yield {'method': 'turn/completed', 'params': {'threadId': 'same-session', 'turn': {'id': str(len(self.calls)), 'status': 'completed'}}}
        else:
            while len(self.calls) <= self.emitted: await asyncio.sleep(0)
            text = self.texts[self.emitted]; self.emitted += 1
            yield {'method': 'session/update', 'params': {'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': text}}}}
            self.ready.set()
            await asyncio.Future()

    async def next_server_request(self, **kwargs): return None


@pytest.mark.parametrize('kind', ['codex', 'kimi', 'deepseek'])
async def test_wrong_work_package_rewrites_immediately_same_native_session(kind):
    work = {'algorithm_md': 'retain this work'}
    bad = valid_decision(research_brief={}, work_package=work)
    good = valid_decision(research_brief={'work_package': work})
    brain = KimiBrain('fixture', 'fixture', 'high') if kind == 'kimi' else CodexBrain('fixture', 'gpt-6-astra', 'xhigh', provider='deepseek' if kind == 'deepseek' else None)
    rpc = NativeRPC([json.dumps(bad), json.dumps(good)], 'kimi' if kind == 'kimi' else 'codex'); brain.rpc = rpc
    before = time.monotonic()
    events = [ev async for ev in brain.review(SessionRef(kind, 'same-session'), {'run_id': 'run_t1'})]
    assert time.monotonic() - before < 3
    assert len(rpc.calls) == 2
    assert all(p.get('threadId', p.get('sessionId')) == 'same-session' for _, p in rpc.calls)
    assert any(e.type == 'progress' and 'work_package' in e.payload['detail'] for e in events)
    assert [e.payload['decision'] for e in events if e.type == 'decision'] == [good]
    assert 'work_package' in json.dumps(rpc.calls[1]) and '未执行' in json.dumps(rpc.calls[1], ensure_ascii=False)


@pytest.mark.parametrize('protocol,contract,good', [
    ('role_task', {'type': 'object', 'required': ['report'], 'properties': {'report': {'type': 'string'}}, 'additionalProperties': False}, {'report': 'ok'}),
    ('experience_curation', None, {'schema_version': 1, 'message_type': 'curation_result', 'summary': 'ok', 'experience_proposals': []}),
    ('executor_question', None, {'schema_version': 1, 'message_type': 'research_answer', 'request_id': 'q1', 'answer_md': 'ok', 'evidence_refs': [], 'native_answers': None}),
])
async def test_each_structured_role_is_checked_before_exposure(protocol, contract, good):
    packet = {'protocol': protocol, 'output_contract': contract}
    class Fake:
        async def _review_once(self, session, current):
            value = good if '_format_feedback' in current else {'misplaced': 1}
            yield structured_output.parse(json.dumps(value), current)
    events = [e async for e in structured_output.review(Fake(), SessionRef('fixture', 'same'), packet)]
    assert len(events) == 2 and events[0].payload['status'] == 'format_rewrite'
    assert events[-1].type != 'error'


async def test_rewrites_are_bounded_and_provider_errors_not_retried():
    class Fake:
        count = 0
        async def _review_once(self, session, packet):
            self.count += 1
            yield structured_output.parse('not JSON', packet)
    fake = Fake(); events = [e async for e in structured_output.review(fake, SessionRef('fixture', 'same'), {})]
    assert fake.count == 3 and events[-1].payload['code'] == 'FORMAT_INVALID'
    class Rate(Fake):
        async def _review_once(self, session, packet):
            self.count += 1
            yield BrainEvent('error', {'message': '429 Retry-After'})
    rate = Rate(); events = [e async for e in structured_output.review(rate, SessionRef('fixture', 'same'), {})]
    assert rate.count == 1 and events[-1].payload['message'].startswith('429')


def test_review_contract_field_errors_and_secret_redaction():
    from cyberscientist import config
    config.save_secrets({'fixture': 'fixture-secret-value'})
    event = structured_output.parse(json.dumps({'schema_version': 1, 'message_type': 'review_result', 'extra': 'fixture-secret-value'}), {'protocol': 'review_result'})
    assert event.payload['code'] == 'FORMAT_INVALID' and 'extra' in event.payload['message']
    assert 'fixture-secret-value' not in event.payload['message']


async def test_kimi_notification_error_is_native_failure_not_rewritten():
    class BrokenRPC(NativeRPC):
        async def notifications(self):
            while not self.calls: await asyncio.sleep(0)
            self.ready.set()
            yield {'method': 'session/update', 'params': {'update': None}}
    brain = KimiBrain('fixture', 'fixture', 'high'); rpc = BrokenRPC([], 'kimi'); brain.rpc = rpc
    events = [e async for e in brain.review(SessionRef('kimi', 'same-session'), {})]
    assert len(rpc.calls) == 1 and events[-1].type == 'error'
    assert '事件流异常' in events[-1].payload['message']


def test_new_research_answer_does_not_bypass_schema_using_legacy_answers():
    value = {'schema_version': 1, 'message_type': 'research_answer', 'answer_md': 'ok', 'answers': {'q': 'a'}}
    event = structured_output.parse(json.dumps(value), {'protocol': 'executor_question'})
    assert event.type == 'error' and 'request_id' in event.payload['message']


async def test_bounded_maintenance_rewrites_are_reserved_before_each_native_turn():
    from cyberscientist import db, maintenance
    from test_mailboxes import _seed_challenge, _make_run
    _seed_challenge(); rid = _make_run()
    maintenance.claim_call(rid, 'first', 'postreview')
    class Fake:
        count = 0
        async def _review_once(self, session, packet):
            self.count += 1
            yield structured_output.parse('not JSON', packet)
    fake = Fake(); structured_output.set_budget(fake, rid, 'maintenance')
    events = [e async for e in structured_output.review(fake, SessionRef('fixture', 'same'), {})]
    assert fake.count == 2 and events[-1].payload['code'] == 'FORMAT_REWRITE_BLOCKED'
    rows = db.query('SELECT * FROM maintenance_calls WHERE run_id=?', (rid,))
    assert len(rows) == 2 and rows[1]['status'] == 'failed'


async def test_zero_probe_single_turn_authorization_cannot_expand_on_bad_format():
    class Fake:
        allow_format_rewrites = False
        count = 0
        async def _review_once(self, session, packet):
            self.count += 1
            yield structured_output.parse('{}', packet)
    fake = Fake(); events = [e async for e in structured_output.review(fake, SessionRef('fixture', 'same'), {})]
    assert fake.count == 1 and events[-1].payload['code'] == 'FORMAT_REWRITE_BLOCKED'


async def test_real_triage_contract_rejects_wrong_fields_on_native_path(monkeypatch):
    from cyberscientist import competition
    from cyberscientist.controller import RunController
    from test_competition import challenges
    challenges(1); rnd = competition.import_round(['c0'], mode='demo')
    good = {'difficulty': 'easy', 'estimated_minutes': 1, 'estimated_cost_cny': None,
        'recommended_model': 'gpt-6.1-sol', 'recommended_solver_id': None, 'reason': 'fixture',
        'priority':0,'data_complete':None}
    bad = {**good, 'estimated_minutes': 'wrong'}
    class NativeBrain(CodexBrain):
        async def open(self, spec): return SessionRef('codex', 'same-session')
        async def close(self, session): pass
    brain = NativeBrain('fixture', 'gpt-6-astra', 'xhigh')
    brain.rpc = NativeRPC([json.dumps(bad), json.dumps(good)], 'codex')
    ctl = RunController(); monkeypatch.setattr(ctl, '_make_brain', lambda settings: brain)
    result = await competition.triage(rnd['id'], ctl)
    assert result['items'][0]['triage'] == good and len(brain.rpc.calls) == 2
    assert 'estimated_minutes' in json.dumps(brain.rpc.calls[1])


@pytest.mark.parametrize('version', [None, '1'])
def test_decision_version_error_names_exact_field(version):
    value = valid_decision()
    if version is None: value.pop('schema_version')
    else: value['schema_version'] = version
    result = structured_output.parse(json.dumps(value), {'run_id': 'run_t1'})
    assert result.payload['code'] == 'FORMAT_INVALID' and 'schema_version' in result.payload['message']
