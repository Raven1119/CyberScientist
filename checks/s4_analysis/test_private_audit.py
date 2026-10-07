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


def test_index_snapshot_audits_staged_bytes_despite_later_working_tree_write(tmp_path):
    import subprocess
    from .verify_private import index_snapshot
    def git(*args):return subprocess.check_output(['git',*args],cwd=tmp_path)
    git('init','-q');path=tmp_path/'data.json';path.write_text('{"safe":true}')
    git('add','data.json');snapshot=index_snapshot(tmp_path)
    path.write_text('{"safe":false}')
    assert git('cat-file','blob',snapshot[path])==b'{"safe":true}'
    assert path.read_text()=='{"safe":false}'
