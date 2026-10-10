import hashlib
import json
from pathlib import Path
from cyberscientist import runtime_release, runtime_snapshot


def test_legacy_caches_move_out_without_losing_bytes(tmp_path):
    root=tmp_path/'comp';original={}
    for name in ('releases/old/manifest.json','release-cache-history/old/proof','previous/old/trace','release-journal/old'):
        path=root/'.runtime'/name;path.parent.mkdir(parents=True,exist_ok=True)
        content=json.dumps({'files':{}}) if name.endswith('.json') else name
        path.write_text(content);original[name]=content
    (root/'.runtime/release-aliases.json').write_text('{"fallback":"old"}')
    outside=runtime_release.migrate_cache(root)
    assert outside==tmp_path/'comp-cache'
    assert all((outside/name).read_text()==body for name,body in original.items())
    assert all(not (root/'.runtime'/name.split('/')[0]).exists() for name in original)
    assert runtime_release.manifest_path(root,'old')==outside/'releases/old/manifest.json'
    assert runtime_release.migrate_cache(root)==outside


def test_existing_cache_collision_preserves_both_versions(tmp_path):
    root=tmp_path/'comp';outside=runtime_release.cache_root(root)
    old=root/'.runtime/releases/version';old.mkdir(parents=True);(old/'proof').write_text('legacy')
    new=outside/'releases/version';new.mkdir(parents=True);(new/'proof').write_text('prior-outside')
    runtime_release.migrate_cache(root)
    assert (new/'proof').read_text()=='legacy'
    assert next((outside/'release-cache-history').glob('migration-*/proof')).read_text()=='prior-outside'
