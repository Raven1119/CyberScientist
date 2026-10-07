"""Offline synthetic regression for installed and publicly discoverable CLI.

No global configuration/install changes. Official CLI copies only; no research
trace or downloaded scientific program is executed.
"""
import json
import subprocess
import tempfile
from pathlib import Path

import httpx
from .common import DEFAULT_DATA,atomic,sha,utcnow,write_json
from .sealed_inputs import pure_diagnostics

PUBLIC='https://api.github.com/repos/Osgood001/playground-cli/commits/main'


def run_variant(cli,source,directory,diag):
    directory.mkdir(parents=True,exist_ok=True);out=directory/'converted.jsonl'
    node=diag._binary('node');env=diag._env(directory,node)
    child=subprocess.run([str(node),str(cli),'trace','convert','--trace',str(source),'--out',str(out)],env=env,
      stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    result={'exit_code':child.returncode,'cli_sha256':sha(cli.read_bytes())}
    if child.returncode==0:
        rows=[json.loads(line) for line in out.read_text().splitlines() if line.strip()]
        calls={r.get('tool_call_id') for r in rows if r.get('step_type')=='tool_call'}
        results={r.get('tool_call_id') for r in rows if r.get('step_type')=='tool_result'}
        result.update(events=len(rows),tool_calls=len(calls),tool_results=len(results),paired_tool_ids=len(calls&results),
          semantic_sha256=sha(json.dumps([{k:v for k,v in r.items() if k not in ['timestamp','step_id']} for r in rows],sort_keys=True).encode()))
    else:result['status']='unknown_converter_failed'
    return result


def main():
    root=DEFAULT_DATA;directory=root/'.raw/converter_synthetic';directory.mkdir(parents=True,exist_ok=True)
    rows=[{'type':'thread.started','thread_id':'synthetic'},
      {'type':'item.started','item':{'id':'cmd1','type':'command_execution','command':'printf synthetic-only'}},
      {'type':'item.completed','item':{'id':'cmd1','type':'command_execution','command':'printf synthetic-only','aggregated_output':'synthetic-only','exit_code':0}},
      {'type':'item.completed','item':{'id':'msg1','type':'agent_message','text':'Synthetic command finished.'}}]
    cli=Path('/home/wmywb/.local/lib/node_modules/@paper2arm/playground-cli/dist/index.js')
    installed_hash=sha(cli.read_bytes());version=json.loads(cli.parent.parent.joinpath('package.json').read_text())['version']
    diag=pure_diagnostics();report={'observed_at':utcnow(),'installed_version':version,'installed_sha256':installed_hash,
      'synthetic_only':True,'network_disabled_during_conversion':True,'no_global_changes':True,'variants':{},'latest_distribution_status':'unknown'}
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        temporary=Path(temp);(temporary/'patched').mkdir();fixed=diag._patched_cli(temporary/'patched')
        for name,events in [('clean',rows),('with_transport_error',rows+[{'type':'error','message':'synthetic transport error'}])]:
            source=temporary/(name+'.jsonl');atomic(source,(''.join(json.dumps(r)+'\n' for r in events)).encode())
            for variant,path in [('installed',cli),('existing_precedence_fix',fixed)]:
                report['variants'][variant+'_'+name]=run_variant(path,source,temporary/(variant+'_'+name),diag)
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            for label,url in [('npm_latest','https://registry.npmjs.org/@paper2arm%2Fplayground-cli/latest'),('public_repository_head',PUBLIC)]:
                try:
                    response=client.get(url)
                    if response.status_code==404:response=client.get(url)
                    report[label]={'url':url,'status':response.status_code,'response_sha256':sha(response.content)}
                    if label=='public_repository_head' and response.status_code==200:
                        commit=response.json()['sha'];report[label]['commit']=commit
                        base='https://raw.githubusercontent.com/Osgood001/playground-cli/'+commit+'/'
                        package=client.get(base+'package.json');report[label]['package_status']=package.status_code
                        if package.status_code==200:report[label]['version']=package.json().get('version')
                        upstream=temporary/'public-main';upstream.mkdir()
                        complete=True
                        for file in ['dist/index.js','dist/task-authoring.js']:
                            r=client.get(base+file)
                            if r.status_code==404:r=client.get(base+file)
                            report[label][file.replace('/','_')+'_status']=r.status_code
                            if r.status_code==200:atomic(upstream/Path(file).name,r.content)
                            else:complete=False
                        if complete:
                            atomic(upstream/'package.json',b'{"type":"module"}')
                            source=temporary/'with_transport_error.jsonl'
                            report['variants']['public_main_with_transport_error']=run_variant(upstream/'index.js',source,temporary/'public-test',diag)
                except Exception as exc:report[label]={'url':url,'status':'unknown','error_kind':type(exc).__name__}
    if sha(cli.read_bytes())!=installed_hash:raise ValueError('Global CLI changed externally during probe')
    bad=report['variants']['installed_with_transport_error'];good=report['variants']['installed_clean']
    report['installed_transport_error_regression_reproduced']=bad.get('paired_tool_ids')==0 and good.get('paired_tool_ids')==1
    write_json(root/'scorer/converter_synthetic_regression.json',report)
    print(json.dumps(report))


if __name__=='__main__':main()
