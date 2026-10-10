import asyncio
import time
import pytest
from cyberscientist import db, gate_reviews, ops
from test_pi_wake_cs21 import setup_run


@pytest.mark.asyncio
async def test_new_alert_wakes_in_seconds_and_old_alert_does_not():
    rid,_,_=setup_run()
    db.append_event(rid,'controller','run.paused',{'reason':'old'})
    async def create_alert():
        await asyncio.sleep(.1)
        db.append_event(rid,'controller','run.blocked',{'reason':'new'})
    task=asyncio.create_task(create_alert());start=time.monotonic()
    result=await ops.wait_alert(3);await task
    assert result['status']=='event' and len(result['alerts'])==1
    assert result['alerts'][0]['kind']=='run.blocked' and time.monotonic()-start<2


@pytest.mark.asyncio
async def test_new_review_item_also_wakes():
    async def add_gate():
        await asyncio.sleep(.1)
        gate_reviews.record('shape','sha',source='fixture')
    task=asyncio.create_task(add_gate())
    result=await ops.wait_alert(3);await task
    assert result['status']=='event' and result['gates'][0]['rule']=='shape'


@pytest.mark.asyncio
async def test_timeout_is_explicit():
    result=await ops.wait_alert(0)
    assert result=={'status':'timeout','text':'无新事件','alerts':[],'gates':[]}
