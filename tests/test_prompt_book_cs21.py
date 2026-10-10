import hashlib
import json
from pathlib import Path
import pytest
from cyberscientist import config, prompt_book


def test_export_reports_literal_conflicts_and_edit_locations(tmp_path):
    path=tmp_path/'pi.md';path.write_text('roles/pi v3\n评分在查什么\n')
    old=hashlib.sha256(b'roles/pi v2\n').hexdigest()
    book=prompt_book.Book(tmp_path,{'files':{'pi.md':old}})
    book.add('PI','题面收敛；旧条目D-49；Job；CODEX_HOME','pi.md')
    markdown,hits=book.finish()
    assert '相对 v2：**有改动**' in markdown
    assert {'收敛','内部编号','Job','凭据路径'} <= {hit['term'] for hit in hits}
    assert all(hit['line']>0 and hit['source']=='pi.md' for hit in hits)
    assert '每段的用户修改落点' in markdown


def test_source_templates_match_real_nested_method(tmp_path):
    (tmp_path/'source.py').write_text('class Role:\n    def render(self):\n        return "literal"\n')
    assert prompt_book.source_function(tmp_path,'source.py','Role.render')=='    def render(self):\n        return "literal"'
    with pytest.raises(ValueError):prompt_book.source_function(tmp_path,'source.py','missing')


def test_server_export_uses_child_process_without_mutating_paths(monkeypatch):
    from types import SimpleNamespace
    original=config.DB_PATH
    def run(command,**kwargs):
        assert command[1:]==['-m','cyberscientist.prompt_book','real_run']
        assert kwargs['timeout']==180 and kwargs['cwd']==config.WORKSPACE_ROOT
        return SimpleNamespace(returncode=0,stdout=json.dumps({'markdown':'rendered','metadata':{}}))
    monkeypatch.setattr(prompt_book.subprocess,'run',run)
    assert prompt_book.dump('real_run')['markdown']=='rendered'
    assert config.DB_PATH==original


def test_handoff_uses_actual_nested_action():
    handoff={'method_md':'real method'}
    assert prompt_book._handoff({'decision':{'actions':[{'clean_handoff':handoff}]}})==handoff
    assert prompt_book._handoff('```json\n'+json.dumps({'actions':[{'clean_handoff':handoff}]})+'\n```')==handoff
