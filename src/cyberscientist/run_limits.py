"""Explicit competition authorization; existing bounded grants stay bounded."""
from . import db
import json


def track_unlimited(run, auth=None):
    """New confirmed track policy; never broaden historical/standalone grants."""
    if auth is None:
        auth=db.query_one('SELECT unlimited_resources FROM authorizations WHERE id=?',(run['authorization_id'],))
    return bool(auth and auth['unlimited_resources'] and
                json.loads(run['config_snapshot']).get('competition',{}).get('budget_policy')=='track-unlimited/v1')


def unlimited(run_id: str, *, conn=None) -> bool:
    sql = ('SELECT a.unlimited_resources FROM authorizations a JOIN runs r '
           'ON r.authorization_id=a.id AND a.run_id=r.id WHERE r.id=?')
    row = conn.execute(sql, (run_id,)).fetchone() if conn else db.query_one(sql, (run_id,))
    return bool(row and row['unlimited_resources'])


def reached(run_id: str, used: int, limit: int) -> bool:
    return not unlimited(run_id) and used >= limit


def displayed(run_id: str, value):
    return None if unlimited(run_id) else value
