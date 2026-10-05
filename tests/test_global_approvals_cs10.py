import pytest
from cyberscientist import db, experiences, experience_context, environment_facts
from cyberscientist.controller import RunController


def meta():
    return {'title':'全局候选','scope':'global','status':'candidate','kind':'heuristic','evidence_status':'hypothesis','evidence_refs':[]}


@pytest.mark.asyncio
async def test_pending_http_version_approve_next_injection_and_reject_requeue():
    from httpx import ASGITransport, AsyncClient
    from cyberscientist.api import create_app
    saved=experiences.save_experience('candidate',meta(),'保底建议','brain','候选',None)
    assert not experience_context.effective(None)
    async with AsyncClient(transport=ASGITransport(app=create_app()),base_url='http://t') as client:
        pending=(await client.get('/api/v1/experiences/pending-approvals')).json()['items']
        assert pending[0]['body_md'].strip()=='保底建议' and pending[0]['revision_id']==saved['revision_id']
        stale=await client.post('/api/v1/experiences/candidate/approve',json={'expected_revision':'old'})
        assert stale.status_code==409 and experiences.pending_approvals()['items']
        assert (await client.post('/api/v1/experiences/candidate/approve',json={'expected_revision':saved['revision_id']})).status_code==200
        assert not experiences.pending_approvals()['items']
        assert experience_context.effective(None)[0]['body_md'].strip()=='保底建议'
        new=experiences.save_experience('candidate',meta(),'候选新版','brain','改进',saved['current_hash'])
        assert (await client.post('/api/v1/experiences/candidate/reject',json={'expected_revision':new['revision_id'],'note':'证据不足'})).status_code==200
        assert not experiences.pending_approvals()['items']
        rejected=experiences.get_experience('candidate')
        experiences.save_experience('candidate',meta(),'补充证据的新版','brain','重提',rejected['current_hash'])
        assert experiences.pending_approvals()['items'][0]['body_md'].strip()=='补充证据的新版'


def test_environment_facts_auto_inject_without_entering_approval_queue():
    db.execute("INSERT INTO challenges(id,origin,title,content,content_hash,imported_at,is_demo) VALUES('ef','fixture','x','x','h',?,1)",(db.utcnow(),))
    rid=RunController().create_run('ef')['id']
    event=db.append_event(rid,'controller','sandbox.environment_observed',{'action':'quota'})
    result=environment_facts.record('quota','额度观察',{'available':2},event)
    assert not experiences.pending_approvals()['items']
    assert result['id'] in {v['id'] for v in experience_context.effective('ef')}
