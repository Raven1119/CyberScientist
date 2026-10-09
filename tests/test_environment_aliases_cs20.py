"""Environment display migration preserves immutable receipts and old choices."""
import hashlib
import json

import pytest

from cyberscientist import capabilities, config, db, environment_catalog as catalog, runtime_environments
from test_environment_catalog_cs10 import descriptor, proof
from test_sandboxes import run


def historical_entry(name):
    evidence = proof()
    data = descriptor(name) | {'status': 'verified', 'receipts': evidence,
        'last_verified_at': evidence[0]['observed_at'], 'restore_seconds': {'sandbox': 1.0}}
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    db.execute('INSERT INTO environment_catalog_entries VALUES(?,?,?,?)', (name, raw, digest, db.utcnow()))
    return raw, digest


def test_startup_migration_keeps_old_bytes_and_receipts_but_indexes_only_canonical_names():
    original = {name: historical_entry(name) for name in catalog.LEGACY_IDS}
    db.init_db()
    before = catalog.items()
    db.init_db()
    assert before == catalog.items()
    assert {item['id'] for item in before} == set(catalog.LEGACY_IDS.values())
    for old, new in catalog.LEGACY_IDS.items():
        assert catalog.get(old) == catalog.get(new)
        raw, digest = original[old]
        row = db.query_one('SELECT * FROM environment_catalog_entries WHERE id=?', (old,))
        assert (row['descriptor_json'], row['sha256']) == (raw, digest)
        assert catalog.get(new)['receipts'] == json.loads(raw)['receipts']
    index_ids = {item['id'] for item in capabilities.index()}
    assert set(catalog.LEGACY_IDS.values()) <= index_ids
    assert not set(catalog.LEGACY_IDS) & index_ids
    summary = capabilities.summary()
    assert not any(old in summary for old in catalog.LEGACY_IDS)


def test_old_choice_restores_same_image_and_receipts_without_rewriting_history(run):
    _, rid, _, _, _ = run
    old = 'cs13-abacus-v2'
    raw, digest = historical_entry(old)
    frozen = {'mode': 'catalog', 'entry_id': old, 'catalog_sha256': digest, 'reason_md': 'Synthetic historical choice'}
    event = db.append_event(rid, 'brain', 'environment.choice', frozen)
    db.init_db()
    plan = catalog.prepare(rid)
    assert plan['choice'] == frozen
    assert plan['entry']['id'] == 'abacus-plane-wave-v2'
    assert plan['entry']['image'] == json.loads(raw)['image']
    assert plan['entry']['receipts'] == json.loads(raw)['receipts']
    assert json.loads(db.query_one('SELECT payload FROM events WHERE run_id=? AND type=?', (rid, 'environment.choice'))['payload']) == frozen
    selected = catalog.choose(rid, {'mode': 'catalog', 'entry_id': old, 'reason_md': 'New choice via old alias'})
    assert selected['entry_id'] == 'abacus-plane-wave-v2'
    assert selected['catalog_sha256'] == catalog.get(old)['sha256']


@pytest.mark.parametrize('conflict', ['descriptor', 'alias'])
def test_collisions_fail_closed_instead_of_redirecting_old_records(conflict):
    old, new = 'cs12-pyscf-v1', 'pyscf-v1'
    historical_entry(old)
    if conflict == 'descriptor':
        changed = descriptor(new); changed['image'] = 'registry.example/other:fixed'
        # Insert directly to represent a pre-existing administrative conflict.
        db.execute('INSERT INTO environment_catalog_entries VALUES(?,?,?,?)',
            (new, json.dumps(changed), 'f'*64, db.utcnow()))
    else:
        historical_entry('other')
        db.execute('INSERT INTO environment_catalog_aliases VALUES(?,?,?)', (old, 'other', db.utcnow()))
    before = db.query('SELECT * FROM environment_catalog_entries ORDER BY id')
    with pytest.raises(ValueError, match='不同'):
        with db.transaction() as conn:
            catalog.migrate_legacy_ids(conn)
    assert db.query('SELECT * FROM environment_catalog_entries ORDER BY id') == before


def test_new_registration_using_legacy_id_returns_canonical_identity():
    data = catalog.register_verified(descriptor('cs10-public-python-v1'), proof())
    assert data['id'] == 'python-3-10-public-v1'
    assert [item['id'] for item in catalog.items()] == [data['id']]


def test_recipe_alias_resolves_without_symlinks_and_rejects_path_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'WORKSPACE_ROOT', tmp_path)
    root = tmp_path / 'environments'
    target = root / 'scientific-runtimes'; target.mkdir(parents=True)
    (target / 'environment.json').write_text(json.dumps({'id': 'scientific-runtimes', 'identity': {'python': '3.10'}}))
    (target / 'Dockerfile').write_text('FROM scratch\n')
    (root / 'aliases.json').write_text(json.dumps({'cs-up-12': 'scientific-runtimes', 'bad': '../secret'}))
    assert runtime_environments.recipe('cs-up-12') == runtime_environments.recipe('scientific-runtimes')
    with pytest.raises(runtime_environments.EnvironmentUnavailable, match='越界'):
        runtime_environments.recipe('bad')
