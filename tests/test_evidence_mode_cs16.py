import json
import pytest
from cyberscientist import config,db,evidence_policy,trace_gate,trace_hints,observation
from cyberscientist.controller import RunController
from cyberscientist.prime import ActionReceipt
from test_mailboxes import _seed_challenge,_make_run
from test_decision import valid_decision

@pytest.mark.parametrize('mode,expected',[('competition',0),('development',1)])
def test_optional_automatic_diagnostics_and_cross_run_scan_follow_frozen_policy(mode,expected,monkeypatch):
    settings=config.load_settings();settings['evidence_mode']=mode;config.save_settings(settings)
    _seed_challenge();rid=_make_run();calls=[]
    monkeypatch.setattr(trace_hints,'inspect',lambda data:calls.append(data) or {'status':'ready','hints':[]})
    evidence_policy.automatic_trace_hint(b'fixture',rid)
    assert len(calls)==expected
    result=trace_gate.cross_run_matches({'x.py':b'fixture'},rid)
    assert result['status']==('not_run' if mode=='competition' else 'observed')
    # Runtime settings changes never alter the evidence policy of an existing Run.
    settings['evidence_mode']='development' if mode=='competition' else 'competition';config.save_settings(settings)
    assert evidence_policy.mode(rid)==mode

@pytest.mark.parametrize('mode,expected',[('competition',1),('development',4)])
async def test_competition_avoids_discarded_legacy_prompt_and_duplicate_memory_body(mode,expected,monkeypatch):
    settings=config.load_settings();settings['evidence_mode']=mode;settings['progressive_context']=True;config.save_settings(settings)
    _seed_challenge();rid=_make_run();db.execute("UPDATE runs SET phase='running',gate='open' WHERE id=?",(rid,))
    original=observation.authority_facts;calls=[]
    def read(r):calls.append(r);return original(r)
    monkeypatch.setattr(observation,'authority_facts',read)
    class Native:
        async def prompt(self,sid,text):return ActionReceipt(status='accepted',detail='fixture')
    ctrl=RunController();ctrl._prime_instances[rid]=Native();ctrl._prime_sessions[rid]='fixture'
    await ctrl._apply_decision(rid,valid_decision(run_id=rid,actions=[{'op':'start_trial','goal':'完整计算','success_check':'产物契约'}]),{},None,None)
    assert len(calls)==expected
    tid=db.query_one('SELECT current_trial_id FROM runs WHERE id=?',(rid,))[0]
    manifest=json.loads((config.WORKSPACE_DIR/'runs'/rid/'trials'/tid/'memory_manifest.json').read_text())
    assert ('source' in manifest)==(mode=='competition')
    stored=db.query_one('SELECT content_json FROM experience_contexts WHERE id=?',(manifest['id'],))
    assert stored and json.loads(stored[0])['sha256']==manifest['sha256']
