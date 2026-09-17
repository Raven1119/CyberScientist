import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
d = json.load(io.open(r'C:\Users\wmywb\AppData\Local\Temp\or-models.json', encoding='utf-8'))
free_tools = []
for m in d['data']:
    mid = m['id']
    if not mid.endswith(':free'):
        continue
    sp = m.get('supported_parameters') or []
    if 'tools' in sp:
        free_tools.append((mid, m.get('context_length'), m.get('name')))
print(f'free models WITH tool support: {len(free_tools)}')
for mid, ctx, name in free_tools[:25]:
    print(f'  {mid:45} ctx={ctx}')
# GLM 详情
for m in d['data']:
    if m['id'].startswith('z-ai/glm'):
        sp = m.get('supported_parameters') or []
        print(f"GLM {m['id']:30} tools={'tools' in sp} free={m['id'].endswith(':free')}")
