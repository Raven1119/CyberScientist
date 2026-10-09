"""Concurrent ledger alerts and strategy updates must not lock out HTTP work."""
import threading

from cyberscientist import alerts, config, db, strategies
from cyberscientist.controller import RunController
from test_collaboration import _seed_challenge


def test_secret_read_completes_while_configuration_mutation_is_held():
    config.update_secret('fixture', 'SYNTHETIC_CONCURRENCY_SECRET')
    held, release, read = threading.Event(), threading.Event(), threading.Event()
    values = []

    def hold_configuration():
        with config.mutation_lock:
            held.set()
            release.wait(5)

    def read_secrets():
        values.append(config.load_secrets())
        read.set()

    holder = threading.Thread(target=hold_configuration)
    reader = threading.Thread(target=read_secrets)
    holder.start()
    assert held.wait(2)
    reader.start()
    try:
        completed = read.wait(1)
    finally:
        release.set()
        holder.join(3)
        reader.join(3)
    assert completed, 'a ledger reader must not wait for the configuration mutation lock'
    assert values == [{'fixture': 'SYNTHETIC_CONCURRENCY_SECRET'}]


def test_alert_transaction_and_strategy_update_do_not_invert_locks(monkeypatch):
    _seed_challenge()
    rid = RunController().create_run('COLLAB_CH')['id']
    run = db.query_one('SELECT * FROM runs WHERE id=?', (rid,))
    entered, alert_done = threading.Event(), threading.Event()
    errors = []
    original = db.query_one

    def gated_query(sql, params=()):
        if threading.current_thread().name == 'strategy-update' and sql.startswith('SELECT * FROM runs'):
            entered.set()  # strategies.update already owns mutation_lock here.
            if not alert_done.wait(2):
                raise RuntimeError('alert holds the ledger while waiting for configuration')
        return original(sql, params)

    monkeypatch.setattr(db, 'query_one', gated_query)

    def worker(action):
        try:
            action()
        except BaseException as exc:
            errors.append(exc)
        finally:
            if hasattr(db._local, 'conn'):
                db._local.conn.close()
                del db._local.conn

    def insert_alert():
        assert entered.wait(2)
        with db.transaction() as conn:
            alerts._insert(conn, 'fixture-concurrency', run, 'run.blocked', 'fixture', {'value': 'safe'})
        alert_done.set()

    writer = threading.Thread(name='strategy-update', target=worker,
                              args=(lambda: strategies.update(rid, brief={'route_md': 'synthetic route'}),))
    reader = threading.Thread(target=worker, args=(insert_alert,))
    writer.start()
    reader.start()
    writer.join(4)
    reader.join(4)
    assert not writer.is_alive() and not reader.is_alive()
    assert not errors, errors
    assert alert_done.is_set()
    assert db.query_one("SELECT 1 FROM alerts WHERE dedupe_key='fixture-concurrency'")
    assert db.query_one('SELECT 1 FROM experience_heads WHERE experience_id=?', (strategies.card_id(rid),))


def test_concurrent_secret_updates_keep_every_value_and_reads_are_complete():
    from concurrent.futures import ThreadPoolExecutor

    def update(index):
        config.update_secret(f'fixture-{index}', f'SYNTHETIC_VALUE_{index}')
        return config.load_secrets()

    with ThreadPoolExecutor(max_workers=4) as pool:
        snapshots = list(pool.map(update, range(20)))
    expected = {f'fixture-{index}': f'SYNTHETIC_VALUE_{index}' for index in range(20)}
    assert config.load_secrets() == expected
    assert all(all(expected[key] == value for key, value in snapshot.items()) for snapshot in snapshots)
