import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
p = r'C:\Users\wmywb\PycharmProjects\CyberScientist\workspace\runs\prime-probe\transcript-redacted.jsonl'
for i, line in enumerate(io.open(p, encoding='utf-8')):
    try:
        d = json.loads(line, strict=False)
    except json.JSONDecodeError:
        print(f'--- [{i}] (truncated line, skipped)')
        continue
    t = d.get('type')
    s = json.dumps(d, ensure_ascii=False)
    print(f'--- [{i}] {t} len={len(s)}')
    if t in ('message_end', 'agent_end', 'turn_end'):
        print(s[:800])
    if t == 'message_update':
        ev = d.get('assistantMessageEvent', {})
        if ev.get('type') in ('error', 'done'):
            print(s[:500])
