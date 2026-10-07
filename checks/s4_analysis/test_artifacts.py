import io
import json
import zipfile

import pytest

from .common import Redactor
from .collect_bundles import sanitize_archive
from .select import select


def archive(files):
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w') as z:
        for name,value in files.items():z.writestr(name,value)
    return target.getvalue()


def test_bundle_secrets_are_scrubbed_before_archive_or_document_persistence():
    value='sk-'+'k'*40
    source=archive({'manifest.json':json.dumps({'credentials':{'default':value}}),
                    'README.md':'A description.', 'src/solve.py':'print(1)',
                    'outputs/data.csv':'x,y\n1,2\n'})
    clean,files,docs=sanitize_archive(source,Redactor())
    with zipfile.ZipFile(io.BytesIO(clean)) as z:
        assert value.encode() not in z.read('manifest.json')
        assert z.read('src/solve.py')==b'print(1)'
    assert len(files)==4 and {d['path'] for d in docs}=={'manifest.json','README.md'}
    manifest=next(f for f in files if f['path']=='manifest.json')
    assert manifest['sha256']!=manifest['sanitized_sha256'] and manifest['redacted']


def test_archive_traversal_is_rejected_before_extraction():
    with pytest.raises(ValueError,match='unsafe_archive'):
        sanitize_archive(archive({'../outside.txt':'anything'}),Redactor())


def test_selection_keeps_author_best_jumps_and_ours_with_explicit_reasons():
    rows=[]
    for aid,author,score,trace,ours in [(1,'a',10,10,False),(2,'a',95,90,False),
                                       (3,'b',90,69,False),(4,'c',0,None,True)]:
        rows.append({'attempt_id':str(aid),'challenge_id':'c','author_id':author,'author_name':author,
                     'display_score':str(score),'science_score':'100','trace_score':str(trace) if trace is not None else None,
                     'trace_decision':'review' if aid==3 else 'accept','created_at':f'2026-08-01T00:0{aid}:00Z',
                     'round_seq':'1','trace_count':'20','ours':ours,'raw.bundleAvailable':None})
    selected,bundles,calibration=select(rows)
    by_id={r['attempt_id']:r for r in selected}
    assert by_id['2']['head_rank']==1 and 'jump_after' in by_id['2']['selection_reasons']
    assert 'jump_before' in by_id['1']['selection_reasons'] and 'head_top10' not in by_id['1']['selection_reasons']
    assert 'ours' in by_id['4']['selection_reasons'] and by_id['4']['semantic_required']
    assert {r['attempt_id'] for r in bundles}=={'2','3'}
