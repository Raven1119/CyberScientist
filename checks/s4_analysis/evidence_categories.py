"""Freeze a model-proposed taxonomy, then classify every distinct missing claim."""
import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed

from .common import DEFAULT_DATA,sha,utcnow,write_json
from .dataset import read_table
from .models import ModelClient
from .tables import write_csv

TAXONOMY_SYSTEM='''Return JSON only. Propose 10-20 mutually understandable factual categories for scorer missing-evidence statements. Classify the KIND OF EVIDENCE REQUESTED, not whether it is actually missing. No strategy, scientific answers, code or advice. Include an other/ambiguous category. Output {"categories":[{"id":"C01", "name":string, "definition":string, "include_examples":array of short generic phrases, "exclude":string}],"scope":string}. Category definitions must not assert misconduct or absence of original work.'''
CLASSIFY_SYSTEM='''Return JSON only. The taxonomy is frozen. Assign each supplied missing-evidence statement to 1-3 category IDs. Classify requested evidence only; a scorer claim is not proof that evidence is absent. Do not solve any scientific task or provide advice. All IDs must be returned exactly once. Output {"labels":[{"id":string,"categories":[string],"confidence":number between 0 and 1}]}.'''


def batches(items,max_items=100,max_chars=32000):
    batch=[];size=0
    for item in items:
        length=len(item['text'])
        if batch and (len(batch)>=max_items or size+length>max_chars):yield batch;batch=[];size=0
        batch.append(item);size+=length
    if batch:yield batch


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=12);args=parser.parse_args()
    root=DEFAULT_DATA;rows=list(read_table('data/missing_evidence.csv'));texts={sha((r['text'] or '').encode()):r['text'] or '' for r in rows}
    folder=root/'data/missing_evidence_labels';folder.mkdir(parents=True,exist_ok=True)
    taxonomy_path=root/'data/missing_evidence_taxonomy.json';client=ModelClient()
    if taxonomy_path.exists():taxonomy=json.loads(taxonomy_path.read_text())
    else:
        # Deterministic, round/topic-spread sample plus frequent recurring text.
        counts=Counter(r['text'] or '' for r in rows);sample=[];seen=set()
        for r in sorted(rows,key=lambda r:sha((r['challenge_id']+r['text']).encode())):
            if r['challenge_id'] not in seen:sample.append(r['text']);seen.add(r['challenge_id'])
        sample+=sorted(texts.values(),key=lambda text:sha(text.encode()))[:150]
        sample+=[text for text,_ in counts.most_common(30)]
        response=client.generate(TAXONOMY_SYSTEM,json.dumps({'sample':sample},ensure_ascii=False),max_tokens=8192)
        categories=response['output'].get('categories',[])
        if not 10<=len(categories)<=20 or len({r['id'] for r in categories})!=len(categories):raise ValueError('Invalid taxonomy')
        taxonomy={'frozen_at':utcnow(),'categories':categories,'scope':response['output'].get('scope'),
                  'model_receipt':{k:v for k,v in response.items() if k!='output'},'status':'frozen_before_batch_classification'}
        write_json(taxonomy_path,taxonomy)
    ids={r['id'] for r in taxonomy['categories']};taxonomy_sha=sha(taxonomy_path.read_bytes());known={}
    for path in folder.glob('*.json'):
        result=json.loads(path.read_text())
        if result.get('taxonomy_sha256')==taxonomy_sha:
            known.update({r['id']:r for r in result['labels'] if r.get('status')=='ok'})
    pending=[{'id':digest,'text':text} for digest,text in sorted(texts.items()) if digest not in known]
    jobs=list(batches(pending));failures=[]
    def one(batch):
        response=ModelClient().generate(CLASSIFY_SYSTEM,json.dumps({'taxonomy':taxonomy['categories'],'statements':batch},ensure_ascii=False),max_tokens=8192)
        labels=response['output'].get('labels',[]);mapping={r.get('id'):r for r in labels if isinstance(r,dict)};output=[]
        for item in batch:
            label=mapping.get(item['id'],{});categories=label.get('categories');confidence=label.get('confidence')
            valid=isinstance(categories,list) and 1<=len(categories)<=3 and set(categories)<=ids and isinstance(confidence,(int,float)) and not isinstance(confidence,bool) and 0<=confidence<=1
            output.append({'id':item['id'],'categories':categories if valid else [],'confidence':confidence if valid else None,
                           'status':'ok' if valid else 'unknown_invalid_model_label'})
        path=folder/(sha(json.dumps([i['id'] for i in batch]).encode())+'.json')
        write_json(path,{'taxonomy_sha256':taxonomy_sha,'labels':output,'model_receipt':{k:v for k,v in response.items() if k!='output'}})
        return output
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(one,batch):batch for batch in jobs}
        for i,f in enumerate(as_completed(futures),1):
            try:known.update({r['id']:r for r in f.result()})
            except Exception as exc:failures.append({'ids':[r['id'] for r in futures[f]],'error_kind':type(exc).__name__})
            if i%10==0 or i==len(futures):
                print(json.dumps({'batches':i,'expected':len(futures),'classified_unique':len(known),'failures':len(failures),'time':utcnow()}),flush=True)
    classified=[]
    for row in rows:
        digest=sha((row['text'] or '').encode());label=known.get(digest,{})
        classified.append({**row,'text_sha256':digest,'category':(label.get('categories') or [None])[0],
          'categories_json':json.dumps(label.get('categories',[])),'category_confidence':label.get('confidence'),
          'classification_status':label.get('status','unknown_model_call_failed'),'taxonomy_sha256':taxonomy_sha})
    write_csv(root/'data/missing_evidence_classification.csv',classified)
    write_json(root/'data/missing_evidence_classification_status.json',{'rows':len(rows),'unique_texts':len(texts),
       'classified_rows':sum(r['classification_status']=='ok' for r in classified),'failures':failures,
       'taxonomy_sha256':taxonomy_sha,'observed_at':utcnow()})
    # Merge into W1 only if its source keys/text still match; final collector may be active.
    latest=list(read_table('data/missing_evidence.csv'))
    if [(r['attempt_id'],r['evidence_index'],r['text']) for r in latest]==[(r['attempt_id'],r['evidence_index'],r['text']) for r in rows]:
        write_csv(root/'data/missing_evidence.csv',classified)


if __name__=='__main__':main()
