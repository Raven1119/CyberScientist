"""Scheduling clock; platform eligibility always uses the original facts."""
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
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


def from_snapshot(snapshot):
    clock=snapshot.get('track_clock',{})
    return {name:instant(clock.get(name)) or platform_time(snapshot,field) for name,field in (('start','roundStartAt'),('end','roundEndAt'))} | {'source':clock.get('source','platform')}


def override(snapshot, values, now=None):
    if not isinstance(values,dict) or set(values)-{'start','end','duration_hours','use_platform'}: raise ValueError('赛道时钟字段不符')
    if values.get('use_platform') is True:
        return {'start':(platform_time(snapshot,'roundStartAt').isoformat() if platform_time(snapshot,'roundStartAt') else None),
                'end':(platform_time(snapshot,'roundEndAt').isoformat() if platform_time(snapshot,'roundEndAt') else None),'source':'platform'}
    now=now or datetime.now(timezone.utc)
    if 'duration_hours' in values:
        hours=values['duration_hours']
        if isinstance(hours,bool) or not isinstance(hours,(int,float)) or not 0<hours<=336: raise ValueError('赛道时长须在0到336小时之间')
        start=now;end=now+timedelta(hours=hours)
    else:
        start=instant(values.get('start'));end=instant(values.get('end'))
        if not start or not end: raise ValueError('赛道开始/结束时间须为有效ISO时间')
    if end<=start: raise ValueError('赛道结束时间必须晚于开始时间')
    return {'start':start.isoformat(),'end':end.isoformat(),'source':'operator_override','updated_at':now.isoformat()}


def facts(snapshot,now=None):
    now=now or datetime.now(timezone.utc);clock=from_snapshot(snapshot)
    return {'start':clock['start'].isoformat() if clock['start'] else None,'end':clock['end'].isoformat() if clock['end'] else None,
            'source':clock['source'],'remaining_seconds':(clock['end']-now).total_seconds() if clock['end'] else None,
            'until_start_seconds':(clock['start']-now).total_seconds() if clock['start'] else None,
            'platform_start':(platform_time(snapshot,'roundStartAt').isoformat() if platform_time(snapshot,'roundStartAt') else None),
            'platform_end':(platform_time(snapshot,'roundEndAt').isoformat() if platform_time(snapshot,'roundEndAt') else None)}


def for_run(run):
    snapshot=json.loads(run['config_snapshot'])
    link=snapshot.get('competition',{}).get('round_id')
    if link:
        row=db.query_one("SELECT config_json FROM eval_runs WHERE id=? AND suite='competition'",(link,))
        if row:
            current=json.loads(row['config_json'])
            return from_snapshot(current) | {'round_id':link}
    return {'start':platform_time(snapshot,'roundStartAt'),'end':platform_time(snapshot,'roundEndAt'),'source':'platform','round_id':None}


def remaining(run, now):
    end=for_run(run)['end']
    return end.timestamp()-now if end else float('inf')
