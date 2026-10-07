"""Prepare sanitized local scorer inputs, preserving unknown worker context."""
import argparse
import io
import json
import os
import subprocess
import time
import zipfile
from pathlib import Path,PurePosixPath

from .common import DEFAULT_DATA,atomic,sha,unzstd,utcnow,write_json
from .dataset import read_table
from . import sealed_inputs

HERE=Path(__file__).resolve().parent


def unpack_bundle(root,aid):
    archive=root/'.raw/bundles'/(aid+'.zip')
    if not archive.exists():return None,None
    buffer=archive.read_bytes();digest=sha(buffer);directory=root/'.raw/unpacked'/aid/digest
    receipt=root/'.raw/unpack_receipts'/(aid+'.json')
    if receipt.exists() and json.loads(receipt.read_text()).get('archive_sha256')==digest and json.loads(receipt.read_text()).get('extraction_revision')==2:
        return str(directory/json.loads(receipt.read_text())['bundle_root']),digest
    with zipfile.ZipFile(io.BytesIO(buffer)) as source:
        infos=source.infolist();names=[]
        for info in infos:
            path=PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or (info.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Unsafe sanitized archive member')
            if info.is_dir():continue
            destination=directory.joinpath(*path.parts)
            if not destination.resolve().is_relative_to(directory.resolve()):raise ValueError('Archive escaped output root')
            atomic(destination,source.read(info));names.append(path)
    common={name.parts[0] for name in names}
    relative=next(iter(common)) if len(common)==1 and all(len(name.parts)>1 for name in names) else '.'
    # Keep the extraction receipt outside the evidence directory when root='.'.
    write_json(root/'.raw/unpack_receipts'/(aid+'.json'),{'archive_sha256':digest,'bundle_root':relative,'extraction_revision':2})
    return str(directory/relative),digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    root=DEFAULT_DATA;prepared=root/'.raw/v6_inputs';outputs=root/'.raw/v6_reports'
    prepared.mkdir(parents=True,exist_ok=True);outputs.mkdir(parents=True,exist_ok=True)
    home=root/'.raw/offline-home';home.mkdir(parents=True,exist_ok=True)
    processed={}
    while True:
        selected=list(read_table('data/selected.csv'))
        additions=root/'data/selection_additions.csv'
        if additions.exists():selected+=list(read_table('data/selection_additions.csv'))
        selected={r['attempt_id']:r for r in selected};manifest=[]
        for aid,item in selected.items():
            path=root/'data/traces'/(aid+'.jsonl.zst')
            if not path.exists():path=root/'.raw/traces'/(aid+'.jsonl.zst')
            if not path.exists():continue
            raw=unzstd(path.read_bytes())
            if not raw.strip() and not (root/'.raw/bundles'/(aid+'.zip')).exists():
                write_json(outputs/(aid+'.json'),{'attempt_id':aid,'status':'unknown_public_trace_empty'})
                processed[aid]=('empty',None);continue
            archive=root/'.raw/bundles'/(aid+'.zip')
            archive_sha=sha(archive.read_bytes()) if archive.exists() else None
            pair=(sha(raw),archive_sha)
            if processed.get(aid)==pair:continue
            topic=json.loads((root/'data/topics'/(item['challenge_id']+'.json')).read_text())
            task='\n\n'.join(str(topic[k]) for k in ['title','topicContent','content'] if topic.get(k))
            task_path=prepared/(item['challenge_id']+'.txt');atomic(task_path,task.encode())
            trace_path=prepared/(aid+'.jsonl');atomic(trace_path,raw);provenance=None
            try:
                if archive.exists():
                    provenance=sealed_inputs.prepare(root,aid,metadata=item)
                    trace_path=Path(provenance['converted_path']);raw=trace_path.read_bytes();unpacked=provenance['output_directory']
                else:unpacked=None
            except Exception as exc:
                write_json(outputs/(aid+'.json'),{'attempt_id':aid,'status':'failed','error_kind':type(exc).__name__});continue
            manifest.append({'attempt_id':aid,'trace':str(trace_path),'trace_sha256':sha(raw),
                             'task':str(task_path),'outputs':unpacked,'out':str(outputs/(aid+'.json')),'input_provenance':provenance})
            processed[aid]=pair
        if manifest:
            manifest_path=prepared/'manifest.json';write_json(manifest_path,manifest)
            env={'HOME':str(home),'PATH':'/home/wmywb/.local/bin:/usr/bin:/bin','LANG':'C.UTF-8'}
            result=subprocess.run(['/home/wmywb/.local/bin/node','--experimental-strip-types',str(HERE/'checklist.mjs'),
                 str(HERE.parents[1]/'src/cyberscientist/vendor/trace_score_cli_v6/index.ts'),str(manifest_path)],
                 env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600)
            # Node prints counts only; errors are represented by status, never raw input.
            print(json.dumps({'prepared':len(manifest),'native_exit':result.returncode,'reports':len(list(outputs.glob('*.json'))),'time':utcnow()}),flush=True)
            if result.returncode:raise RuntimeError('Pinned v6 batch failed; no model score inferred')
        if not args.watch:break
        time.sleep(30)


if __name__=='__main__':main()
