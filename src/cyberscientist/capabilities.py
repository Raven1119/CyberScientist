"""Fresh, bounded capabilities; observations never grant spending authority."""
import json
from . import db, environment_catalog, machine_catalog, sandbox_warmup, skills


def _names(values, limit):
    picked = []
    for value in values:
        if len(','.join(picked + [value])) > limit:
            return ','.join(picked) + f'（共{len(values)}项，完整目录另查）'
        picked.append(value)
    return ','.join(picked)


def summary(run_id: str | None = None) -> str:
    entries = environment_catalog.items()
    warm = {x['entry_id']: x['created_success_at'] for x in sandbox_warmup.latest()}
    catalog = skills.scan_catalog()
    lines = ['能力事实（非授权；未知保持unknown）：']
    for prefix in ('bohrium-', 'cyberscientist-'):
        names = [x['id'][len(prefix):] for x in catalog if x['id'].startswith(prefix)]
        lines.append('技能ID前缀' + prefix + '：' + _names(names, 250))
    lines.append('环境ID：' + _names([e['id'] for e in entries], 350))
    lines.append('镜像/包/冒烟完整事实：research_environment list/restore；计算：research_job/research_sandbox；LKM：research_lkm。')
    for channel, fact in machine_catalog.facts().items():
        names = [x.get('skuEnName') or x.get('sku_name') for x in fact['items']]
        names = list(filter(None, names))
        lines.append(f"GPU {channel}={_names(names, 100) or 'unknown'}；观察={fact.get('observed_at') or 'unknown'}；库存/授权另核实")
    auth = db.query_one('SELECT a.*,r.config_snapshot FROM authorizations a JOIN runs r ON r.authorization_id=a.id WHERE r.id=?', (run_id,)) if run_id else None
    limits = '尚无Run授权'
    if auth:
        unlimited = bool(auth['unlimited_resources'])
        limits = {k: None if unlimited else auth[k] for k in ('max_jobs', 'max_sandboxes', 'max_compute_cost_cny')}
        limits.update(unlimited_resources=unlimited, allow_sandbox_gpu=bool(auth['allow_sandbox_gpu']))
        snapshot = json.loads(auth['config_snapshot'])
        caps = snapshot.get('operator_submission_limits', snapshot.get('settings', {}).get('policy', {}).get('submission_limits', {}))
        if caps: limits['submission_limits'] = caps
    tail = ('授权=' + json.dumps(limits, ensure_ascii=False) +
            '\nunlimited_resources=true时，数量null表示不限；提交以独立额度为准。\n本地仅编排；科研在Bohrium。PI简报明确镜像、技能及CPU/GPU选择；执行器读取SKILL.md后通过受控bohr使用。')
    out = '\n'.join(lines)
    # Show the chosen environment, then recent distinct images. Alphabetical
    # truncation previously hid newly verified materials/ABACUS environments.
    chosen = environment_catalog.current(run_id).get('entry_id') if run_id else None
    ranked = sorted(entries, key=lambda e: (e['id'] == chosen, e['last_verified_at']), reverse=True)
    images = set()
    for entry in ranked:
        if entry['image'] in images: continue
        images.add(entry['image'])
        line = (f"环境 {entry['id']}={entry['image']}；验证={entry['last_verified_at']}；"
                f"耗时={entry['restore_seconds']}；预热={warm.get(entry['id']) or 'unknown'}")
        if len(out) + len(line) + len(tail) + 2 <= 2000:
            out += '\n' + line
    return out + '\n' + tail


def index(run_id=None):
    """Names, one-line purposes and read locations; no environment recipes."""
    entries=[]
    for item in skills.scan_catalog():
        if item['id'].startswith(('bohrium-','cyberscientist-')):
            entries.append({'id':item['id'],'use':' '.join(item['description'].split())[:140],
                            'location':str(__import__('pathlib').Path(item['source'])/item['id']/'SKILL.md')})
    for item in environment_catalog.items():
        entries.append({'id':item['id'],'use':'已登记环境起点，先读取当前验证事实','location':'research_environment list: '+item['id']})
    entries.extend({'id':name,'use':purpose,'location':name} for name,purpose in (
        ('research_job','提交重计算Job'),('research_sandbox','持续交互环境'),
        ('research_environment','环境目录与恢复'),('research_lkm','公开科学摘要检索'),
        ('research_web_search','网页检索'),('research_web_read','读取网页'),
        ('research_experience','按ID读取经验正文')))
    return entries
