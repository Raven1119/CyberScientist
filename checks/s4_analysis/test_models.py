import json

from . import common,models


def test_cached_model_text_is_rescrubbed_without_another_provider_call(tmp_path,monkeypatch):
    monkeypatch.setattr(common,'credentials',lambda:({},'',{}))
    client=models.ModelClient();client.cache=tmp_path;calls=[]
    def response(_):
        calls.append(True)
        return {'content':json.dumps({'text':'clean'}),'provider_model':'fixture','usage':{'total_tokens':1}}
    monkeypatch.setattr(client,'_deepseek',response)
    first=client.generate('system','user')
    path=tmp_path/(first['request_sha256']+'.json');old=json.loads(path.read_text())
    value='opaque-'+'q'*32;old['output']['text']=json.dumps({'envdAccessToken':value})
    path.write_text(json.dumps(old))
    second=client.generate('system','user')
    assert len(calls)==1 and value not in json.dumps(second) and value not in path.read_text()


def test_truncated_response_is_not_retried_with_identical_token_budget(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setattr(common,'credentials',lambda:({},'',{}));monkeypatch.setattr(models,'DEFAULT_DATA',tmp_path)
    client=models.ModelClient();client.cache=tmp_path/'cache';client.cache.mkdir();calls=[]
    def response(_):calls.append(True);raise ValueError('Model_output_truncated')
    monkeypatch.setattr(client,'_deepseek',response)
    with pytest.raises(RuntimeError,match='Model_output_truncated'):client.generate('system','user')
    with pytest.raises(RuntimeError,match='Model_output_truncated'):client.generate('system','user')
    assert len(calls)==1
    def larger(settings):
        calls.append(True);assert settings['max_tokens']==8192
        return {'content':'{}','provider_model':'fixture'}
    monkeypatch.setattr(client,'_deepseek',larger)
    client.generate('system','user',max_tokens=8192)
    assert len(calls)==2
