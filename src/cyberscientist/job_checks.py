"""Mandatory, nonexecuting Job checks followed by receipt-backed image checks."""
from __future__ import annotations

import ast
import hashlib
import json
import math
import posixpath
import py_compile
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from . import db, job_preflight

Error = job_preflight.PreflightError
_BUILTINS = {'if','then','else','elif','fi','for','while','do','done','case','esac','in',
             'set','echo','printf','test','[',':','true','false','exit','export','cd','pwd',
             'read','wait','trap','return','break','continue','source','.'}
_NETWORK = re.compile(r'(?<![\w/])(?:curl|wget)\s|\bgit\s+clone\b|\b(?:pip(?:3)?\s+install|uv\s+pip\s+install|conda\s+install)\b')


def _shell_units(text: str, source: str, python_sources: dict[str,str], generated: dict[str,str]) -> list[str]:
    """Separate here-document data and unwrap constant shell/Python commands."""
    lines=text.splitlines();units=[];index=0
    while index<len(lines):
        line=lines[index];index+=1
        heredoc=re.search(r"<<(-?)\s*(['\"]?)([A-Za-z_]\w*)\2",line)
        if heredoc:
            body=[];delimiter=heredoc[3]
            while index<len(lines) and (lines[index].lstrip('\t') if heredoc[1] else lines[index])!=delimiter:
                body.append(lines[index]);index+=1
            index+=1
            if re.search(r'\bpython[0-9.]*\b',line):python_sources[f'_inline_{len(python_sources)}.py']='\n'.join(body)+'\n'
            elif re.search(r'\bcat\b',line):
                target=re.search(r'>\s*([A-Za-z0-9_./-]+)',line)
                if target:generated[target[1]]='\n'.join(body)+'\n'
            line=line[:heredoc.start()]+line[heredoc.end():]
        parse_line=re.sub(r'\d*>&\d+', '>/dev/null',line)
        lexer=shlex.shlex(parse_line,posix=True,punctuation_chars=';&|');lexer.whitespace_split=True;lexer.commenters='#'
        try:tokens=list(lexer)
        except ValueError:units.append(line);continue
        segments=[];segment=[]
        for token in tokens:
            if token in (';','&&','||','|','&'):
                if segment:segments.append(segment);segment=[]
            else:segment.append(token)
        if segment:segments.append(segment)
        for parts in segments:
            if parts and Path(parts[0]).name in ('bash','sh') and any(flag in parts for flag in ('-c','-lc')):
                flag='-c' if '-c' in parts else '-lc';position=parts.index(flag)
                if len(parts)>position+1:
                    units.append(shlex.join(parts[:position]))
                    units.extend(_shell_units(parts[position+1],source,python_sources,generated));continue
            if parts and re.fullmatch(r'python[0-9.]*',Path(parts[0]).name) and '-c' in parts:
                position=parts.index('-c')
                if len(parts)>position+1:python_sources[f'_inline_{len(python_sources)}.py']=parts[position+1]
            units.append(' '.join(part if part in ('>','>>','<','2>','2>>','&>') else shlex.quote(part) for part in parts))
    return units


def _executables(tokens: list[str]) -> list[str]:
    """Collect wrappers and the executable they launch, without running shell."""
    result=[];parts=list(tokens)
    while parts:
        while parts and (parts[0] in ('then','do','!') or re.match(r'^[A-Za-z_]\w*=',parts[0])):parts.pop(0)
        if not parts:break
        executable=parts.pop(0);result.append(executable);base=Path(executable).name
        if base in ('mpirun','mpiexec','srun'):
            while parts and parts[0].startswith('-'):
                option=parts.pop(0)
                if option in ('-np','-n','--np','--ntasks','-N','--host','--hostfile','-hostfile','-x','--map-by','--bind-to') and parts:parts.pop(0)
            continue
        if base=='timeout':
            while parts and parts[0].startswith('-'):
                option=parts.pop(0)
                if option in ('-s','--signal','-k','--kill-after') and parts:parts.pop(0)
            if parts:parts.pop(0)
            continue
        if base=='env':
            while parts and (parts[0].startswith('-') or re.match(r'^[A-Za-z_]\w*=',parts[0])):parts.pop(0)
            continue
        if base=='time':
            while parts and parts[0].startswith('-'):
                option=parts.pop(0)
                if option in ('-o','--output','-f','--format') and parts:parts.pop(0)
            continue
        break
    return result


def static(files: dict[str, bytes], spec: dict, options: dict) -> dict:
    command = str(spec.get('command') or '')
    texts = {name: raw.decode('utf-8','replace') for name,raw in files.items()}
    if not isinstance(options.get('outputs',[]),list) or not isinstance(options.get('required_paths',[]),list):
        raise Error('INVALID_PREFLIGHT','outputs和required_paths必须为列表')
    outputs = set(options.get('outputs') or [])
    inline={};generated={}
    shell_units=[('command',unit) for unit in _shell_units(command,'command',inline,generated)]
    for name,text in list(texts.items()):
        if name.endswith('.sh'):shell_units.extend((name,unit) for unit in _shell_units(text,name,inline,generated))
    texts.update(inline);texts.update(generated)
    if any(not isinstance(name,str) for name in outputs):
        raise Error('INVALID_OUTPUTS','outputs必须为文件路径列表')
    commands=set();paths=set(options.get('required_paths') or []);packages=set();warnings=[];embedded=[]
    if any(not isinstance(name,str) or not name.startswith('/') or '..' in Path(name).parts for name in paths):
        raise Error('INVALID_IMAGE_PATH','镜像路径必须为规范绝对路径')
    # py_compile checks syntax without importing or executing scientific code.
    with tempfile.TemporaryDirectory(prefix='cs-job-syntax-') as directory:
        for name,text in texts.items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise Error('INVALID_SOURCE_PATH','输入文件路径越界')
            path=Path(directory)/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            if name.endswith('.py'):
                try:py_compile.compile(str(path),doraise=True)
                except py_compile.PyCompileError as exc:raise Error('INVALID_PYTHON',f'Python语法错误：{name}') from exc
                tree=ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node,ast.Import):roots=[alias.name.split('.')[0] for alias in node.names]
                    elif isinstance(node,ast.ImportFrom) and not node.level:roots=[(node.module or '').split('.')[0]]
                    else:roots=[]
                    for root in roots:
                        parent=PurePosixPath(name).parent
                        if root and root not in sys.stdlib_module_names and root+'.py' not in files and root+'/__init__.py' not in files and str(parent/(root+'.py')) not in files and str(parent/root/'__init__.py') not in files:packages.add(root)
                    if isinstance(node,ast.Call):
                        label=ast.unparse(node.func)
                        if label in ('subprocess.run','subprocess.Popen','subprocess.call','subprocess.check_call','subprocess.check_output','os.system') and node.args:
                            value=node.args[0]
                            if isinstance(value,ast.Constant) and isinstance(value.value,str):embedded.append((name,value.value))
                            elif isinstance(value,(ast.List,ast.Tuple)):
                                embedded.append((name,' '.join(str(x.value) if isinstance(x,ast.Constant) else 'python' if ast.unparse(x)=='sys.executable' else '$dynamic' for x in value.elts)))
                            else:warnings.append(f'动态执行命令需冒烟核实：{name}:{node.lineno}')
                        if label in ('requests.get','requests.post','urllib.request.urlopen','urllib.request.urlretrieve'):
                            raise Error('NETWORK_REQUIRED',f'Job无网络；请预置数据：{name}:{node.lineno}')
                        if node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
                            target=node.args[0].value
                            if label in ('open','io.open') and len(node.args)>1 and isinstance(node.args[1],ast.Constant) and any(c in str(node.args[1].value) for c in 'wax'):
                                outputs.add(target)
                            if label.endswith(('.save','.savetxt','.savez','.write_text','.write_bytes')) and label.startswith(('np.','numpy.')):outputs.add(target)
                        if isinstance(node.func,ast.Attribute) and node.func.attr in ('write_text','write_bytes'):
                            value=node.func.value
                            if isinstance(value,ast.Call) and value.args and isinstance(value.args[0],ast.Constant) and isinstance(value.args[0].value,str):outputs.add(value.args[0].value)
            if name.endswith('.sh'):
                result=subprocess.run(['bash','-n',str(path)],capture_output=True,text=True,timeout=10)
                if result.returncode:raise Error('INVALID_BASH',f'Bash语法错误：{name}',{'stderr':result.stderr[:2000]})
        result=subprocess.run(['bash','-n','-c',command],capture_output=True,text=True,timeout=10)
        if result.returncode:raise Error('INVALID_BASH','Job命令语法错误',{'stderr':result.stderr[:2000]})
    shell=shell_units+embedded
    cwd_by_source={}
    functions={m[1] for _,text in shell for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\(\)\s*\{',text)}
    for name,text in shell:
        for line in text.splitlines():
            stripped=line.strip()
            if not stripped or stripped.startswith('#'):continue
            offline_install='--no-index' in line and not re.search(r'(?<![\w/])(?:curl|wget)\s|\bgit\s+clone\b',line)
            if _NETWORK.search(line) and not offline_install:
                raise Error('NETWORK_REQUIRED',f'Job无网络；请预置依赖或文件：{name}',{'line':stripped[:300]})
            if re.search(r"\b(?:cp|mv|cat|bash|python\d*)\b[^\n]*'[^']*\$\{[^}]+\}[^']*'",line):
                raise Error('LITERAL_VARIABLE_PATH',f'单引号阻止路径变量展开：{name}',{'line':stripped[:300]})
            for match in re.finditer(r'(?<![\d>])(?:>|>>|\btee\s+)\s*([\w./-]+)',line):
                target=match[1]
                if not target.startswith('/dev/'):outputs.add(target)
            for segment in (line,):
                try:tokens=shlex.split(segment,comments=True)
                except ValueError:continue  # Multiline quoting was checked by bash -n.
                while tokens and (tokens[0] in ('then','do','!') or re.match(r'^[A-Za-z_]\w*=',tokens[0])):tokens.pop(0)
                if not tokens:continue
                executable=tokens[0]
                if executable=='cd' and len(tokens)>1:
                    cwd_by_source[name]=posixpath.normpath(str(PurePosixPath(cwd_by_source.get(name,'.'))/tokens[1]));continue
                if executable in functions or executable.endswith('()'):continue
                launched_commands=_executables(tokens)
                for launched in launched_commands:
                    if launched not in _BUILTINS:commands.add(launched)
                if launched_commands and launched_commands[-1]!=tokens[0]:
                    tokens=tokens[tokens.index(launched_commands[-1]):];executable=tokens[0]
                if executable in _BUILTINS or executable.startswith(('$','(',')','{','}')):continue
                if executable.startswith('./'):
                    if executable[2:] not in files:raise Error('MISSING_ENTRY','执行脚本未打包：'+executable)
                else:commands.add(executable)
                if executable.startswith('/'):paths.add(executable)
                if Path(executable).name in ('bash','sh') or re.fullmatch(r'python[0-9.]*',Path(executable).name):
                    if len(tokens)>1 and not tokens[1].startswith('-'):
                        entry=tokens[1]
                        if not entry.startswith('/') and '$' not in entry:
                            resolved=posixpath.normpath(str(PurePosixPath(cwd_by_source.get(name,'.'))/entry))
                            if resolved not in texts:raise Error('MISSING_ENTRY','入口文件未打包：'+resolved)
                            cwd_by_source.setdefault(resolved,cwd_by_source.get(name,'.'))
                if Path(executable).name=='timeout':
                    for token in tokens[1:]:
                        if token.startswith('-') or re.fullmatch(r'[0-9.]+[smhd]?',token):continue
                        commands.add(token);break
    if 'abacus' in {Path(c).name for c in commands} and not any(Path(name).name=='INPUT' for name in texts):
        raise Error('ABACUS_INPUT_MISSING','ABACUS必须预先打包可检查的INPUT')
    for name,text in texts.items():
        if Path(name).name=='INPUT':
            params={parts[0].lower():parts[1] for line in text.splitlines() if (parts:=line.split('#')[0].split()) and len(parts)>1}
            if 'abacus' in {Path(c).name for c in commands}:
                required={'calculation','basis_type','ecutwfc','scf_thr','scf_nmax'}
                missing=sorted(required-params.keys())
                if missing:raise Error('ABACUS_INPUT_MISSING','ABACUS关键参数缺失',{'missing':missing,'file':name})
            for key in ('pseudo_dir','orbital_dir'):
                if params.get(key,'').startswith('/'):paths.add(params[key])
            if params.get('calculation') in ('relax','cell-relax'):
                stru_name=str(PurePosixPath(name).parent/'STRU');stru=texts.get(stru_name)
                if stru is None:raise Error('ABACUS_STRU_MISSING','弛豫需要同目录STRU')
                positions=stru.split('ATOMIC_POSITIONS',1)
                movable=[]
                if len(positions)==2:
                    for line in positions[1].splitlines():
                        parts=line.split('#')[0].split()
                        if len(parts)>=6:
                            try:[float(x) for x in parts[:3]]
                            except ValueError:continue
                            flags=parts[4:7] if parts[3]=='m' else parts[3:6]
                            if len(flags)==3 and all(x in ('0','1') for x in flags):movable.append(any(x=='1' for x in flags))
                if not movable or not any(movable):raise Error('ABACUS_FIXED_ATOMS','弛豫原子可动标志缺失或全为0')
    backward=spec.get('backward_files')
    if not isinstance(backward,list) or not backward or any(not isinstance(x,str) or not x for x in backward):raise Error('OUTPUTS_NOT_REGISTERED','backward_files必须登记产物')
    import fnmatch
    missing=[name for name in sorted(outputs) if not any(fnmatch.fnmatch(name,pattern) or name.startswith(pattern.rstrip('/')+'/') for pattern in backward)]
    if missing:raise Error('OUTPUTS_NOT_REGISTERED','脚本产物未登记backward_files',{'missing':missing})
    smoke=options.get('smoke_seconds')
    if smoke is None:warnings.append('没有冒烟耗时，时限适配尚未验证')
    elif type(smoke) not in (int,float) or not math.isfinite(smoke) or smoke<=0:raise Error('INVALID_SMOKE_TIME','冒烟耗时必须为正数')
    elif type(spec.get('max_run_time')) is not int or spec['max_run_time']*60 < smoke*3:raise Error('INSUFFICIENT_TIME','Job时限须至少为冒烟耗时的3倍')
    return {'commands':sorted(commands),'paths':sorted(paths),'third_party':sorted(packages),'warnings':warnings,'syntax_checked':True,'outputs':sorted(outputs)}


def image(run_id: str, image_address: str, report: dict) -> dict:
    row=db.query_one('SELECT facts_json FROM image_facts WHERE image_address=? ORDER BY observed_at DESC LIMIT 1',(image_address,))
    facts=json.loads(row['facts_json']) if row else {}
    required={'commands':report['commands'],'paths':report['paths'],'packages':report['third_party']}
    missing={key:[item for item in values if not facts.get(key,{}).get(item)] for key,values in required.items()}
    if any(missing.values()):
        from . import topic_workspace,sandboxes
        chosen=topic_workspace.current(run_id);sid=chosen.get('sandbox_id')
        if not sid or chosen.get('image')!=image_address:
            raise Error('IMAGE_FACTS_MISSING','镜像命令、路径或依赖未经验证；需要同镜像快速沙箱探测',{'missing':missing})
        probe="import importlib,json,os,shutil\nrequired="+repr(required)+"\nout={'commands':{},'paths':{},'packages':{}}\nfor x in required['commands']: out['commands'][x]=shutil.which(x) or False\nfor x in required['paths']: out['paths'][x]=os.path.exists(x)\nfor x in required['packages']:\n try: m=importlib.import_module(x);out['packages'][x]={'version':getattr(m,'__version__',None)}\n except Exception: out['packages'][x]=False\nprint(json.dumps(out,sort_keys=True))"
        from . import compute
        compute._authorized(db.get_db(),run_id)
        result=sandboxes.execute(run_id,sid,'python3 -c '+shlex.quote(probe),min(30,sandboxes._seconds_left(sandboxes._owned(run_id,sid))),'preflight_'+__import__('uuid').uuid4().hex)
        node=sandboxes._data(sandboxes._body(result['receipt']))
        try:observed=json.loads(node['stdout'])
        except (TypeError,KeyError,ValueError):observed={}
        if result['status']!='completed' or result['exit_code']!=0 or not all(isinstance(observed.get(k),dict) for k in required):raise Error('IMAGE_PROBE_UNKNOWN','镜像快速探测未得到完整回执，未创建Job')
        for key in required:facts[key]=facts.get(key,{})|observed[key]
        raw=json.dumps(facts,sort_keys=True);digest=hashlib.sha256(raw.encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO image_facts VALUES(?,?,?,?,?)',(image_address,digest,raw,result['operation_id'],db.utcnow()))
        db.append_event(run_id,'controller','image_facts.observed',{'operation_id':result['operation_id'],'facts_sha256':digest,'source':'owned_same_image_sandbox'})
    missing={key:[item for item in values if not facts.get(key,{}).get(item)] for key,values in required.items()}
    if any(missing.values()):raise Error('IMAGE_REQUIREMENT_MISSING','镜像缺少命令、路径或依赖',{'missing':missing})
    return report|{'image_checked':True}
