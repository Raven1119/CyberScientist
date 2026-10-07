"""Fresh, bounded capabilities; observations never grant spending authority."""
import json
from . import config, db, environment_catalog, machine_catalog, sandbox_warmup, skills


def summary(run_id: str | None = None) -> str:
    settings = config.load_settings()
    entries = environment_catalog.items()
    warm = {x['entry_id']: x['created_success_at'] for x in sandbox_warmup.latest()}
    lines = ['能力事实（非授权；未知保持unknown）：',
             '技能：' + ','.join(x['id'] for x in skills.scan_catalog()
                                if x['id'].startswith(('bohrium-', 'cyberscientist-')))]
    for entry in entries:
        lines.append(f"环境 {entry['id']}={entry['image']}；验证={entry['last_verified_at']}；"
                     f"耗时={entry['restore_seconds']}；预热={warm.get(entry['id']) or 'unknown'}")
    machines = machine_catalog.facts()
    for channel, fact in machines.items():
        names = [x.get('skuEnName') or x.get('sku_name') for x in fact['items']]
        lines.append(f"GPU {channel}={','.join(filter(None, names)) or 'unknown'}；"
                     f"观察={fact.get('observed_at', 'unknown')}；库存/本Run授权另核实")
    auth = db.query_one('SELECT a.* FROM authorizations a JOIN runs r ON r.authorization_id=a.id WHERE r.id=?', (run_id,)) if run_id else None
    limits = ({k: auth[k] for k in ('max_jobs', 'max_sandboxes', 'allow_sandbox_gpu', 'max_compute_cost_cny')}
              if auth else '尚无Run授权')
    tail = ('授权=' + json.dumps(limits, ensure_ascii=False) +
            '\n本地仅编排；科研在Bohrium。PI简报明确镜像、技能及CPU/GPU选择；执行器读取SKILL.md后通过受控bohr使用。')
    # Keep complete lines rather than clipping a registry URI or authority field.
    out = lines[0]
    for line in lines[1:]:
        if len(out) + len(line) + len(tail) + 60 > 2000:
            out += '\n其余环境/技能请读取完整目录。'
            break
        out += '\n' + line
    return out + '\n' + tail
