"""Versioned environment facts from controller-observed receipts only."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from . import config, db, experiences
from .bohr_proxy import redact


def _id(fact_key: str) -> str:
    return 'env_'+hashlib.sha256(fact_key.encode()).hexdigest()[:24]


def _body(data: object) -> str:
    safe=redact(json.dumps(data,ensure_ascii=False,sort_keys=True,default=str),
                config.load_secrets().values())[:6000]
    return f"来自真实回执的环境观察；仅代表观察时状态。\n\n```json\n{safe}\n```"


def needs_refresh(fact_key: str, data: object) -> bool:
    row=db.query_one('SELECT r.frontmatter,r.body_md FROM experience_heads h'
                     ' JOIN experience_revisions r ON r.id=h.head_revision_id'
                     ' WHERE h.experience_id=?',(_id(fact_key),))
    if not row or row['body_md'].strip()!=_body(data).strip(): return True
    fm=json.loads(row['frontmatter'])
    if fm.get('status')!='active': return True
    try: deadline=datetime.fromisoformat(fm['recheck_after'].replace('Z','+00:00'))
    except (KeyError,ValueError): return True
    if deadline.tzinfo is None: deadline=deadline.replace(tzinfo=timezone.utc)
    return deadline<=datetime.now(timezone.utc)+timedelta(days=1)


def record(fact_key: str, title: str, data: object, event: dict) -> dict:
    """Write or refresh an active fact; `save_experience` verifies the event ref."""
    if not event or event.get('source')!='controller' or event.get('type') not in (
            'image_facts.observed','sandbox.environment_observed','environment.host_observed',
            'environment.save_observed','environment.smoke_observed'):
        raise experiences.ExperienceError('INVALID_EVIDENCE','环境事实需要控制器回执事件')
    if not isinstance(fact_key,str) or not fact_key or len(fact_key)>500:
        raise experiences.ExperienceError('INVALID_EXPERIENCE','环境事实键无效')
    event_ref=f"event:{event['run_id']}:{event['seq']}"
    observed=datetime.fromisoformat(event['recorded_at'])
    if observed.tzinfo is None: observed=observed.replace(tzinfo=timezone.utc)
    body=_body(data)
    exp_id=_id(fact_key)
    fm={'id':exp_id,'title':title[:180],'scope':'global','status':'active',
        'evidence_status':'observed','kind':'environment','audience':'both',
        'tags':['environment'],'applicability':'以最近一次回执和复核时间为准',
        'evidence_refs':[event_ref],'observed_at':observed.isoformat(),
        'source':event_ref,'recheck_after':(observed+timedelta(days=7)).isoformat()}
    try:
        prior=experiences.get_experience(exp_id)
    except experiences.ExperienceError as exc:
        if exc.code!='NOT_FOUND': raise
        prior=None
    if prior and prior['body_md'].strip()==body.strip() and \
            prior['frontmatter']['status']=='active':
        recheck=datetime.fromisoformat(prior['frontmatter']['recheck_after'])
        if recheck>datetime.now(timezone.utc)+timedelta(days=1):
            return {'id':exp_id,'unchanged':True}
    return experiences.save_experience(exp_id,fm,body,'system_environment',
                                      f"回执 {event_ref} 更新环境事实",
                                      prior['current_hash'] if prior else None)


def expire_due() -> int:
    """Demote stale facts without changing the observed receipt or old revisions."""
    rows=db.query("SELECT r.experience_id,r.frontmatter FROM experience_heads h"
                  " JOIN experience_revisions r ON r.id=h.head_revision_id"
                  " WHERE h.active_revision_id=h.head_revision_id AND r.applied=1")
    expired=0
    for row in rows:
        fm=json.loads(row['frontmatter'])
        if fm.get('kind')!='environment': continue
        try: deadline=datetime.fromisoformat(fm['recheck_after'].replace('Z','+00:00'))
        except (KeyError,ValueError): continue
        if deadline.tzinfo is None: deadline=deadline.replace(tzinfo=timezone.utc)
        if deadline>datetime.now(timezone.utc): continue
        try:
            current=experiences.get_experience(row['experience_id'])
        except experiences.ExperienceError:
            # A locally edited fact remains excluded by reconciliation; one
            # bad file must not prevent other facts from expiring.
            continue
        next_fm=dict(current['frontmatter'])
        next_fm['status']='candidate'
        next_fm['review_note']='待复核：真实回执超过 recheck_after；新回执到来前不注入'
        experiences.save_experience(row['experience_id'],next_fm,current['body_md'],
                                    'system_environment','到期待复核',current['current_hash'])
        expired+=1
    return expired
