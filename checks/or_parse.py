import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
d = json.load(io.open(r'C:\Users\wmywb\AppData\Local\Temp\or-models.json', encoding='utf-8'))
for m in d['data']:
    if m['id'] == 'deepseek/deepseek-v4.1-flash':
        p = m.get('pricing', {})
        print('id:', m['id'])
        print('name:', m.get('name'))
        print('context:', m.get('context_length'))
        print('pricing per token: prompt', p.get('prompt'), 'completion', p.get('completion'))
        print('supported_parameters:', m.get('supported_parameters'))
