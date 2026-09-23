import json

from cyberscientist import db, experiences, observation
from test_collaboration import _seed_challenge
from cyberscientist.controller import RunController


def frame(rid, end):
    return observation.build_frame(rid,mode="requested",frame_id="test-frame",
        from_seq=1,through_seq=end,shadow_cfg={})


def test_event_pagination_does_not_claim_unread_tail():
    _seed_challenge(); c=RunController(); rid=c.create_run("COLLAB_CH")["id"]
    for i in range(1000): db.append_event(rid,"executor","heartbeat",{"i":i})
    tail=db.append_event(rid,"executor","prime.error",{"error":"tail error"})
    end=tail["seq"]
    db.append_event(rid,"executor","prime.error",{"error":"future excluded"})
    f=frame(rid,end)
    assert any(e["seq"]==end for e in f["notable_events"])
    assert f["processed_through_seq"] == end
    assert all(e["seq"]<=end for e in f["notable_events"])


def test_only_end_snapshot_is_availability_not_adoption():
    _seed_challenge(); c=RunController(); rid=c.create_run("COLLAB_CH")["id"]
    db.execute("UPDATE runs SET experience_snapshot=? WHERE id=?",
       (json.dumps({"at_end":{"items":[{"id":"late","revision_hash":"v1"}]}}),rid))
    assert c._experience_usage("COLLAB_CH")["late"][0]["semantics"] == "availability_only"
    assert "best_score" not in c._experience_usage("COLLAB_CH")["late"][0]


def test_frozen_revision_and_explicit_adoption_link_only_later_results():
    from cyberscientist import experience_context as context
    _seed_challenge(); c=RunController(); rid=c.create_run("COLLAB_CH")["id"]
    fm={"id":"exp_frozen","scope":"challenge","challenge_id":"COLLAB_CH",
        "title":"tailored","kind":"heuristic","status":"active","evidence_status":"contradicted",
        "tags":[],"evidence_refs":[],"derived_from":[],"applicability":"only under assumptions"}
    r=experiences.save_experience("exp_frozen",fm,"original","user",None,None)
    frozen=context.freeze(rid,"trial_one","trial:trial_one")
    item=frozen["items"][0]
    assert item["evidence_status"]=="contradicted" and item["applicability"]
    experiences.save_experience("exp_frozen",fm,"edited later","user",None,r["current_hash"])
    assert context.for_trial(rid,"trial_one")["items"][0]["body_md"].strip()=="original"
    declaration={"context_id":frozen["id"],"experience_id":"exp_frozen","revision_id":item["revision_id"]}
    with db.transaction() as conn:
        context.adopt_tx(conn,rid,"trial_one",[declaration],"executor","checkpoint:fake")
    uses=db.query("SELECT * FROM experience_uses WHERE run_id=?",(rid,))
    assert len(uses)==1 and uses[0]["revision_id"]==item["revision_id"]
    assert uses[0]["semantics"]=="reported"
    with db.transaction() as conn:
        context.adopt_tx(conn,rid,"trial_one",[declaration],"executor","checkpoint:fake")
    assert len(db.query("SELECT * FROM experience_uses"))==1


def test_final_score_and_correction_bind_original_submission_after_cancel(monkeypatch):
    from cyberscientist import mailboxes
    from test_submission_integrity import setup_run
    rid,path=setup_run()
    sub=mailboxes.submit_experiment(rid,'trial_mb1',path,'final-score')
    db.execute("UPDATE runs SET phase='cancelled' WHERE id=?",(rid,))
    platform=mailboxes._platform()
    value=[0.5]
    monkeypatch.setattr(platform,'fetch_score',lambda *a:value[0])
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    assert mailboxes.poll_scores(rid)['updated']==1
    assert mailboxes.poll_scores(rid)['updated']==0
    value[0]=0.75
    assert mailboxes.poll_scores(rid)['updated']==1
    end=db.query_one('SELECT MAX(seq) AS s FROM events WHERE run_id=?',(rid,))['s']
    feedback=frame(rid,end)
    assert len(feedback['metrics'])==2
    assert feedback['metrics'][-1]['package_sha256']==sub['package_sha256']
    assert feedback['metrics'][-1]['trial_id']=='trial_mb1'
    assert 'official_score' not in feedback['quality']['unknown_fields']
    assert db.query_one('SELECT phase FROM runs WHERE id=?',(rid,))['phase']=='cancelled'
    assert not db.query('SELECT * FROM review_requests WHERE run_id=?',(rid,))


def test_topic_entries_keep_evidence_labels_within_budget():
    from cyberscientist import experience_context as context
    from test_experience_integrity import meta
    for i in range(8):
        result=experiences.save_experience(f'global_{i}',meta(), 'global '*500,'user',None,None)
        experiences.approve_experience(f'global_{i}',expected_revision=result['revision_id'])
    experiences.save_experience('topic',meta(scope='challenge',challenge_id='CH1',status='active',
        evidence_status='hypothesis',applicability='only CH1'), 'topic '*500,'user',None,None)
    selected=context.select('CH1',budget=3000)
    assert selected[0]['id']=='topic' and selected[0]['evidence_status']=='hypothesis'
    assert len(context.encode(selected))<=3000


def test_adoption_links_only_subsequent_submission_and_rebuilds(monkeypatch):
    from cyberscientist import experience_context as context, mailboxes
    from test_submission_integrity import setup_run
    from test_experience_integrity import meta
    rid,path=setup_run(limit=3)
    early=mailboxes.submit_experiment(rid,'trial_mb1',path,'before-adoption')
    experiences.save_experience('used',meta(scope='challenge',challenge_id='MB_CH',status='active'),
                                'test learning','user',None,None)
    bundle=context.freeze(rid,'trial_mb1','trial:trial_mb1')
    item=bundle['items'][0]
    declaration={'context_id':bundle['id'],'experience_id':'used','revision_id':item['revision_id']}
    with db.transaction() as conn:
        context.adopt_tx(conn,rid,'trial_mb1',[declaration],'executor','checkpoint:reported')
    later=mailboxes.submit_experiment(rid,'trial_mb1',path,'after-adoption')
    platform=mailboxes._platform()
    monkeypatch.setattr(platform,'fetch_score',lambda *a:0.9)
    monkeypatch.setattr(mailboxes,'_platform',lambda:platform)
    mailboxes.poll_scores(rid)
    links=[e for e in db.events_after(rid,0) if e['type']=='experience.result_linked']
    assert len(links)==1 and links[0]['payload']['submission_id']==later['id']
    assert links[0]['payload']['revision_id']==item['revision_id']
    assert links[0]['payload']['submission_id'] != early['id']
    usage=RunController()._experience_usage('MB_CH')['used']
    assert usage[0]['results'][0]['submission_id']==later['id']
    context.rebuild_uses(rid)
    assert len(db.query('SELECT * FROM experience_uses WHERE run_id=?',(rid,)))==1
