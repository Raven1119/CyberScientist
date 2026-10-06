"""Scheduling clock; platform eligibility always uses the original facts."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from . import db


def instant(value):
    if not isinstance(value,str): return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError: return None


def platform_time(snapshot, field):
    if isinstance(snapshot,str):
        try: snapshot=json.loads(snapshot)
        except (ValueError,TypeError): return None
    if isinstance(snapshot,dict):
        direct=instant(snapshot.get(field))
        if direct: return direct
        for child in snapshot.values():
            found=platform_time(child,field)
            if found: return found
    elif isinstance(snapshot,list):
        for child in snapshot:
            found=platform_time(child,field)
            if found: return found
    return None


def for_run(run):
    snapshot=json.loads(run['config_snapshot'])
    link=snapshot.get('competition',{}).get('round_id')
    if link:
        row=db.query_one("SELECT config_json FROM eval_runs WHERE id=? AND suite='competition'",(link,))
        if row:
            current=json.loads(row['config_json'])
            clock=current.get('track_clock',{})
            return {'start':instant(clock.get('start')) or platform_time(current,'roundStartAt'),
                    'end':instant(clock.get('end')) or platform_time(current,'roundEndAt'),
                    'source':clock.get('source','platform'),'round_id':link}
    return {'start':platform_time(snapshot,'roundStartAt'),'end':platform_time(snapshot,'roundEndAt'),'source':'platform','round_id':None}


def remaining(run, now):
    end=for_run(run)['end']
    return end.timestamp()-now if end else float('inf')
