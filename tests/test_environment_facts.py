"""Role-specific experience delivery and receipt-backed environment facts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from cyberscientist import curation, db, environment_facts, experience_context, experiences, observation
from cyberscientist.controller import RunController
from cyberscientist.experiences import ExperienceError


def _run() -> str:
    db.execute(
        "INSERT INTO challenges(id,platform_challenge_id,origin,title,content,"
        "content_hash,contract_status,imported_at,is_demo)"
        " VALUES(?,?,?,?,?,?,'unknown',?,1)",
        ('AUD_CH','AUD_1','demo://aud','Audience','Test role filtering','hash',db.utcnow()))
    return RunController().create_run('AUD_CH',shadow_enabled=False)['id']


def _experience(name: str, audience: str | None) -> None:
    fm={'title':name,'scope':'challenge','challenge_id':'AUD_CH',
        'status':'active','evidence_status':'observed','kind':'heuristic',
        'evidence_refs':[]}
    if audience is not None:
        fm['audience']=audience
    experiences.save_experience(name,fm,f'{name} body','user','test',None)


def test_brain_and_executor_receive_only_their_audience():
    rid=_run()
    _experience('brain_only','brain')
    _experience('executor_only','executor')
    _experience('legacy_both',None)
    frame=observation.build_frame(rid,mode='shadow',frame_id='audience-frame',
        from_seq=1,through_seq=1,shadow_cfg={'max_reviews':8})
    assert {e['id'] for e in frame['experiences']}=={'brain_only','legacy_both'}
    RunController()._snapshot_memory(rid,'trial_aud',{})
    frozen=experience_context.for_trial(rid,'trial_aud')
    assert {e['id'] for e in frozen['items']}=={'executor_only','legacy_both'}
    assert all(e['audience']=='both' for e in frozen['items'] if e['id']=='legacy_both')


def test_environment_fact_revisions_expire_and_reject_agent_edits():
    rid=_run()
    event=db.append_event(rid,'controller','sandbox.environment_observed',{'action':'quota'})
    first=environment_facts.record('quota','Sandbox quota',{'available':2},event)
    eid=first['id']
    current=experiences.get_experience(eid)
    assert current['frontmatter']['status']=='active'
    assert current['frontmatter']['scope']=='global'
    assert current['frontmatter']['audience']=='both'
    assert current['frontmatter']['source']==f"event:{rid}:{event['seq']}"
    assert eid in {e['id'] for e in experiences.active_experiences('AUD_CH')}
    with pytest.raises(ExperienceError,match='环境事实'):
        experiences.save_experience('forged',{'title':'forged','scope':'global',
            'status':'active','evidence_status':'observed','kind':'environment'},
            'forged','brain','proposal',None)
    with pytest.raises(ExperienceError,match='环境事实'):
        experiences.save_experience(eid,current['frontmatter'],'tampered',
                                    'user','edit',current['current_hash'])
    with pytest.raises(ExperienceError,match='环境事实'):
        experiences.approve_experience(eid,expected_revision=current['revision_id'])
    second_event=db.append_event(rid,'controller','sandbox.environment_observed',{'action':'quota'})
    environment_facts.record('quota','Sandbox quota',{'available':1},second_event)
    updated=experiences.get_experience(eid)
    assert len(updated['revisions'])==2
    assert updated['frontmatter']['source']==f"event:{rid}:{second_event['seq']}"
    assert '"available": 1' in updated['body_md']
    fm=dict(updated['frontmatter'])
    fm['recheck_after']=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    experiences.save_experience(eid,fm,updated['body_md'],'system_environment',
                                'test expiry',updated['current_hash'])
    assert environment_facts.expire_due()==1
    expired=experiences.get_experience(eid)
    assert expired['frontmatter']['status']=='candidate'
    assert '待复核' in expired['frontmatter']['review_note']
    assert len(expired['revisions'])==4
    assert eid not in {e['id'] for e in experiences.active_experiences('AUD_CH')}
    path=experiences._load_current(eid)[0]
    path.write_text(path.read_text().replace('"available": 1','"available": 9'))
    assert experiences.list_experiences()['errors']


def test_environment_requires_registered_controller_receipt():
    rid=_run()
    fake={'run_id':rid,'seq':999,'source':'controller',
          'type':'environment.host_observed','recorded_at':db.utcnow()}
    with pytest.raises(ExperienceError) as exc:
        environment_facts.record('host','Host',{'host':'example'},fake)
    assert exc.value.code=='INVALID_EVIDENCE'


def test_curation_protocol_rejects_environment_proposal():
    import json
    proposal={'scope':'global','challenge_id':None,'title':'not a receipt','body_md':'false',
              'applicability':'all','evidence_refs':[],'kind':'environment'}
    result={'schema_version':1,'message_type':'curation_result','summary':'x',
            'experience_proposals':[proposal]}
    assert curation.extract(json.dumps(result)) is None
    proposal['kind']='heuristic'
    from test_review_defects_cs12 import reviewed
    result['experience_proposals']=[reviewed(proposal)]
    assert curation.extract(json.dumps(result)) is not None
