"""Offline experience migration. Preview by default; --apply takes the workspace lock.

Run with the repository Python environment. Never starts a runtime or calls a platform.
"""
from __future__ import annotations

import argparse
import json
import sqlite3

from cyberscientist import config, db, experiences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply:
        config.acquire_workspace_lock()
    with sqlite3.connect(f'file:{config.DB_PATH}?mode=ro', uri=True) as conn:
        columns = [row[1] for row in conn.execute('PRAGMA table_info(experience_revisions)')]
        active = conn.execute("SELECT id,phase FROM runs WHERE phase NOT IN ('finished','failed','cancelled')").fetchall()
        before = conn.execute('SELECT COUNT(*) FROM experience_revisions').fetchone()[0]
    if active:
        raise SystemExit('Refusing migration while nonterminal Runs exist; use normal Run controls first.')
    result = {'migration_needed': 'parent_revision_id' not in columns,
              'revisions_before': before, 'applied': args.apply}
    if args.apply:
        db.init_db()  # Backs up the legacy database and experience before DDL.
        problems = experiences.check_pending_writes()
        listing = experiences.list_experiences()
        result.update(revisions_after=db.query_one('SELECT COUNT(*) AS n FROM experience_revisions')['n'],
                      entries=len(listing['items']), pending_errors=problems,
                      file_errors=listing['errors'])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
