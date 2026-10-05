"""Explicit competition authorization; existing bounded grants stay bounded."""
from . import db


def unlimited(run_id: str, *, conn=None) -> bool:
    sql = ('SELECT a.unlimited_resources FROM authorizations a JOIN runs r '
           'ON r.authorization_id=a.id AND a.run_id=r.id WHERE r.id=?')
    row = conn.execute(sql, (run_id,)).fetchone() if conn else db.query_one(sql, (run_id,))
    return bool(row and row['unlimited_resources'])


def reached(run_id: str, used: int, limit: int) -> bool:
    return not unlimited(run_id) and used >= limit


def displayed(run_id: str, value):
    return None if unlimited(run_id) else value
