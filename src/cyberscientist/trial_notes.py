"""Automatic topic notes summarize ledger observations, never turn raw Trace into truth."""
from __future__ import annotations
import json
from . import db, experiences
from .observation import strip_secrets


def record(run_id: str, trial_id: str) -> dict | None:
    trial = db.query_one('SELECT * FROM trials WHERE id=? AND run_id=?', (trial_id, run_id))
    if not trial or trial['status'] not in ('done', 'reported_complete', 'interrupted'):
        return None
    run = db.query_one('SELECT challenge_id FROM runs WHERE id=?', (run_id,))
    score = db.query_one("SELECT id,science_score,score_source,scorer_version FROM local_scores WHERE run_id=?"
                         " AND trial_id=? AND score_source IN ('system','executor_verified')"
                         ' ORDER BY science_score DESC LIMIT 1', (run_id, trial_id))
    cp = db.query_one('SELECT id,report FROM checkpoints WHERE run_id=? AND trial_id=?'
                      ' ORDER BY created_at DESC LIMIT 1', (run_id, trial_id))
    events = db.query("SELECT seq FROM events WHERE run_id=? AND trial_id=? AND type IN"
                       " ('trial.done','trial.reported_complete','trial.interrupted','trial.created')", (run_id, trial_id))
    refs = [f"event:{run_id}:{event['seq']}" for event in events]
    if cp:
        refs.append('checkpoint:' + cp['id'])
    if score:
        refs.append('local_score:' + score['id'])
    body = ('做：沿本 Trial 已保存的产物与验证器继续核对；复用已记录的版本和路径。\n'
            '别做：把执行器完成声明或 unknown 分数当成科学成功。\n\n'
            f"Trial 目标：{trial['goal']}\n状态：{trial['status']}（流程状态，不是科学正确性）\n\n"
            '关键数值与验证器：\n' + (json.dumps(dict(score), ensure_ascii=False) if score else 'unknown；无正式验证分') +
            '\n\n执行器交付摘要（声明，需用验证器核对）：\n' + (cp['report'][:2400] if cp else '无检查点摘要') +
            '\n\n证据：\n' + '\n'.join(refs) + '\n')
    body = strip_secrets(body)
    eid = 'trial_note_' + trial_id
    try:
        prior = experiences.get_experience(eid)
    except experiences.ExperienceError as exc:
        if exc.code != 'NOT_FOUND':
            raise
        prior = None
    if prior and prior['body_md'].strip() == body.strip():
        return {'id': eid, 'unchanged': True}
    fm = {'id': eid, 'title': 'Trial 关键记录：' + trial_id, 'scope': 'challenge',
          'challenge_id': run['challenge_id'], 'kind': 'procedure', 'status': 'active',
          'audience': 'both', 'evidence_status': 'hypothesis', 'evidence_refs': refs,
          'tags': ['trial_note'], 'applicability': '本题后续验证；检查点摘要是执行器声明'}
    saved = experiences.save_experience(eid, fm, body, 'system_trial_note', 'Trial 结束自动补记',
                                       prior['current_hash'] if prior else None)
    db.append_event(run_id, 'controller', 'experience.trial_noted', {'trial_id': trial_id,
        'experience_id': eid, 'revision_id': saved['revision_id']}, trial_id=trial_id)
    return saved


def record_closed(run_id: str) -> None:
    for trial in db.query('SELECT id FROM trials WHERE run_id=?', (run_id,)):
        try:
            record(run_id, trial['id'])
        except (experiences.ExperienceError, OSError, ValueError, TypeError) as exc:
            db.append_event(run_id, 'controller', 'experience.trial_note_unknown', {
                'trial_id': trial['id'], 'reason': getattr(exc, 'code', type(exc).__name__)})
