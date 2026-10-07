import json

from . import common
from .verify_private import audit_value


def test_flattened_scientific_identifiers_remain_typed_but_real_keys_fail_audit(monkeypatch):
    monkeypatch.setattr(common,'credentials',lambda:({},'',{}))
    redactor=common.Redactor();identifier='scientific-identifier-with-structure'
    value=audit_value({'resources':json.dumps([{'key':identifier}]),
                       'raw.resultsJson.answers':json.dumps([{'token':identifier}])})
    assert redactor.obj(value)==value
    unsafe=audit_value({'resources':json.dumps([{'key':'sk-'+'a'*40}])})
    assert redactor.obj(unsafe)!=unsafe
