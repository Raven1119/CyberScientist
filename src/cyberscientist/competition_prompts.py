"""Versioned track advice, independently frozen for each started Run."""
from __future__ import annotations
import difflib
import hashlib
import json
import re
from . import db, observation, config


def latest(round_id):
    row = db.query_one('SELECT version,content_md,sha256,created_at FROM competition_prompt_versions WHERE eval_id=? ORDER BY version DESC LIMIT 1', (round_id,))
    return dict(row) if row else {'version':0,'content_md':'','sha256':hashlib.sha256(b'').hexdigest(),'created_at':None}


@config.serialized_mutation
def publish(round_id, content, base_version):
    if not isinstance(content,str) or len(content)>50000 or observation.strip_secrets(content)!=content:
        raise ValueError('用户提示词须为不含密钥的文本，最多50000字')
    if type(base_version) is not int or base_version<0: raise ValueError('提示词版本无效')
    with db.transaction() as conn:
        if not conn.execute("SELECT 1 FROM eval_runs WHERE id=? AND suite='competition'",(round_id,)).fetchone():
            raise ValueError('赛道不存在')
        current=conn.execute('SELECT MAX(version) FROM competition_prompt_versions WHERE eval_id=?',(round_id,)).fetchone()[0] or 0
        if current!=base_version: raise ValueError('提示词版本冲突，请重新读取')
        sha=hashlib.sha256(content.encode()).hexdigest()
        conn.execute('INSERT INTO competition_prompt_versions VALUES(?,?,?,?,?)',(round_id,current+1,content,sha,db.utcnow()))
        conn.execute('UPDATE eval_runs SET updated_at=? WHERE id=?',(db.utcnow(),round_id))
    return latest(round_id)


def section(content, topic_ids, known_ids):
    """General preface plus exact `## <topic ID>` sections; other headings stay."""
    chunks=re.split(r'(?m)^(##[ \t]+[^\n]+)\n',content)
    recognized=False; general=chunks[0]; selected=[]
    for index in range(1,len(chunks),2):
        title=chunks[index][3:].strip(); body=chunks[index+1]
        if title in topic_ids:
            recognized=True; selected.append(chunks[index]+'\n'+body)
        elif title in known_ids:
            recognized=True
        else:
            general+=chunks[index]+'\n'+body
    return general+'\n'.join(selected) if recognized else content


def freeze(round_id, challenge_id):
    value=latest(round_id)
    row=db.query_one('SELECT platform_challenge_id FROM challenges WHERE id=?',(challenge_id,))
    known=db.query('SELECT c.id,c.platform_challenge_id FROM challenges c JOIN eval_results e ON e.challenge_id=c.id WHERE e.eval_id=?',(round_id,))
    known_ids={value for entry in known for value in (entry['id'],entry['platform_challenge_id']) if value}
    return {**value,'content_md':section(value['content_md'],{challenge_id,row['platform_challenge_id'] if row else ''},known_ids),
            'notice':'用户建议；可采纳，也可依据真实证据不采纳并说明理由'}


def packet(run):
    competition=json.loads(run['config_snapshot']).get('competition',{})
    round_id=competition.get('round_id')
    if not round_id: return None
    current=freeze(round_id,run['challenge_id'])
    frozen=competition.get('user_prompt',current)
    delivered=db.query_one('SELECT version,content_md FROM competition_prompt_deliveries WHERE run_id=?',(run['id'],))
    previous=dict(delivered) if delivered else frozen
    changed=current['version']>previous['version']
    return {**current,'label':'用户更新' if changed else '用户建议',
            'diff_md': ''.join(difflib.unified_diff(previous.get('content_md','').splitlines(True),current['content_md'].splitlines(True),fromfile='上次用户建议',tofile='用户更新')) if changed else '',
            'before_research_brief':True,'frozen_version':frozen['version'],
            'initial_content_md':frozen.get('content_md','') if delivered is None else None}


def received(run_id,value):
    if value is None: return
    with db.transaction() as conn:
        conn.execute('INSERT INTO competition_prompt_deliveries VALUES(?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET version=excluded.version,content_md=excluded.content_md,received_at=excluded.received_at WHERE excluded.version>=competition_prompt_deliveries.version',
                     (run_id,value['version'],value['content_md'],db.utcnow()))
        db.append_event_tx(conn,run_id,'brain','competition.prompt_received',{'version':value['version'],'sha256':value['sha256'],'label':value['label']})
