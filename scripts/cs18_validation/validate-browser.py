import json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];area=ROOT/'.runtime/validation/hidden'
def call(action,args):
 req=urllib.request.Request('http://127.0.0.1:10086/command',data=json.dumps({'session':'cs-night-1009','action':action,'args':args}).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
nav=call('navigate',{'url':'http://localhost:8765','newTab':False})
time.sleep(2)
snapshot=call('snapshot',{})
(area/'browser.json').write_text(json.dumps({'navigate':nav,'snapshot':snapshot},ensure_ascii=False,indent=2))
assert nav.get('ok') and snapshot.get('ok') and 'CyberScientist' in snapshot.get('data',{}).get('title','')
assert '工作台' in json.dumps(snapshot,ensure_ascii=False)
print(json.dumps({'opened':True,'title':snapshot['data']['title']}))
