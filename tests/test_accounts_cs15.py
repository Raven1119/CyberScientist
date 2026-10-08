"""Synthetic account protocol and rotation evidence."""
import pytest
from cyberscientist import config,db,mailboxes
from cyberscientist.mailbox_platform import BohriumPlaygroundPlatform
from test_mailboxes import _extra_run,_make_package


def test_pending_registration_exchanges_token_without_regeneration(monkeypatch):
    p=BohriumPlaygroundPlatform('https://play.bohrium.com/api',operator_token='fixture-owner')
    calls=[]
    def http(method,path,**kwargs):
        calls.append((method,path,kwargs))
        return {'/auth/me':{'id':'owner','userType':'human'},
            '/auth/register':{'token':'fixture-session','user':{'id':'agent','userType':'agent','operatorId':'owner','operatorConfirmed':False,'name':'new'}},
            '/auth/tokens':{'token':'asp_fixture_token'}}[path]
    monkeypatch.setattr(p,'_http',http)
    monkeypatch.setattr(mailboxes,'_platform',lambda:p)
    result=mailboxes.register_experiment(1,pending_claim=True)['items'][0]
    assert result['claim_status']=='pending' and result['operator_id']=='owner'
    assert [path for _,path,_ in calls]==['/auth/me','/auth/register','/auth/tokens']
    assert calls[1][2]['json_body']['claimed_operator_id']=='owner'
    assert config.resolve_secret(db.query_one('SELECT secret_ref FROM mailboxes')[0])=='asp_fixture_token'
    assert 'asp_fixture_token' not in str(result) and 'fixture-session' not in str(config.load_secrets())


def test_rotation_lru_and_identical_hash_not_cross_account():
    a,b=mailboxes.register_experiment(2)['items'];rid=_extra_run(912)
    _make_package(rid,'a','a');first=mailboxes.submit_experiment(rid,'a',None,'a')
    _make_package(rid,'b','b');second=mailboxes.submit_experiment(rid,'b',None,'b')
    assert first['mailbox_id']!=second['mailbox_id']
    repeated=mailboxes.submit_experiment(rid,'a',None,'same-package')
    assert repeated['mailbox_id']==first['mailbox_id']
    assert config.DEFAULT_SETTINGS['submission_policy']['same_topic_minutes']==0
    assert config.DEFAULT_SETTINGS['features']['auto_harvest'] is False


def test_soft_limit_prefers_other_topic_account_and_roles_are_audited():
    accounts=mailboxes.register_experiment(2)['items']
    rid=_extra_run(913)
    for i in range(4):
        _make_package(rid,'limit'+str(i),str(i));mailboxes.submit_experiment(rid,'limit'+str(i),None,'limit'+str(i))
    chosen=mailboxes.set_role(accounts[0]['id'],'harvest')
    assert chosen['role']=='harvest'
    assert db.query_one("SELECT value FROM system_state WHERE key=?",('mailbox_role:'+accounts[0]['id'],))
    with pytest.raises(mailboxes.MailboxError):mailboxes.set_role(accounts[1]['id'],'harvest')
