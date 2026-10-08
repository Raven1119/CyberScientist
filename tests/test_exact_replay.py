"""A noise baseline must upload the identical frozen ARM bytes again."""
from __future__ import annotations

import pytest

from cyberscientist import config, db, mailboxes
from test_mailboxes import _set_scored
from test_trace_narrative import _fixture


def test_exact_replay_preserves_frozen_bytes_and_uses_new_attempt(monkeypatch):
    rid, tid, package, files, rows, *_ = _fixture()
    monkeypatch.setattr(mailboxes.arm_admission, 'check',
                        lambda *_: {'verdict': 'admitted', 'signals': {}})
    mailboxes.register_experiment(1)
    source = mailboxes.submit_experiment(rid, tid, None, 'source-for-replay',
                                         prediction_md='科学分预计为 20')
    with pytest.raises(mailboxes.MailboxError) as error:
        mailboxes.submit_exact_replay(source['id'], 'replay-too-early',
                                      '相同包预计得分相同')
    assert error.value.code == 'INVALID_STATE'
    _set_scored(source['id'], 20)
    replay = mailboxes.submit_exact_replay(source['id'], 'replay-once',
                                           '原包字节不变，预计轨迹分在评审噪声内')
    original = (config.WORKSPACE_DIR / source['package_path']).read_bytes()
    repeated = (config.WORKSPACE_DIR / replay['package_path']).read_bytes()
    assert repeated == original
    assert replay['package_sha256'] == source['package_sha256']
    assert replay['replay_of'] == source['id'] and replay['variant_of'] is None
    assert replay['id'] != source['id'] and replay['platform_ref']
    assert mailboxes.submit_exact_replay(source['id'], 'replay-once',
        '原包字节不变，预计轨迹分在评审噪声内')['deduplicated'] is True
    with pytest.raises(mailboxes.MailboxError) as conflict:
        mailboxes.submit_exact_replay(source['id'], 'replay-once', '不同预测')
    assert conflict.value.code == 'CONFLICT'
    events = db.query("SELECT payload FROM events WHERE run_id=? AND type='submission.replay_created'", (rid,))
    assert len(events) == 1


def test_same_hash_replay_cannot_change_account_when_original_is_full():
    from test_auto_harvest import seed
    from cyberscientist import config,db,mailboxes
    rid,source=seed(100)
    settings=config.load_settings();settings['mailbox']['submission_limit']=1;config.save_settings(settings)
    mailboxes.register_experiment(1)
    import pytest
    with pytest.raises(mailboxes.MailboxError,match='邮箱'):
        mailboxes.submit_exact_replay(source['id'],'cannot-change-account','same original version')
    assert not db.query_one("SELECT 1 FROM submissions WHERE operation_id='cannot-change-account'")
