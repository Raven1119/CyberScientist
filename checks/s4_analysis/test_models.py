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
