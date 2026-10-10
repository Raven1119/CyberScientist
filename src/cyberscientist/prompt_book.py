"""Export actual runtime model inputs in an isolated copy, without model calls."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from . import config


def source_function(root, relative, name):
    text = (Path(root) / relative).read_text()
    def visit(nodes, prefix=''):
        for node in nodes:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + node.name
                if qualified == name:
                    return '\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])
                found = visit(node.body, qualified + '.')
                if found is not None:
                    return found
        return None
    result = visit(ast.parse(text).body)
    if result is None:
        raise ValueError('Prompt source function not found: ' + relative + ':' + name)
    return result


class Book:
    def __init__(self, root, baseline):
        self.root = Path(root)
        self.baseline = baseline
        self.parts = []
        self.fragments = []

    def add(self, title, text, source, function='', *, dependencies=(), note='', code=False):
        text = str(text)
        anchor = 'fragment-' + str(len(self.fragments)+1)
        digest = hashlib.sha256(text.encode()).hexdigest()
        paths = [*dependencies] if function else [source, *dependencies]
        changes = []
        for path in paths:
            file = self.root / path
            old = self.baseline.get('files', {}).get(path)
            if file.is_file():
                current = hashlib.sha256(file.read_bytes()).hexdigest()
                changes.append('未收录于 v2 基线' if old is None else '有改动' if old != current else '无改动')
        if function:
            old = self.baseline.get('functions', {}).get(source+':'+function)
            current = hashlib.sha256(source_function(self.root, source, function).encode()).hexdigest()
            changes.append('未收录于 v2 基线' if old is None else '有改动' if old != current else '无改动')
        change = '有改动' if '有改动' in changes else '未收录于 v2 基线' if '未收录于 v2 基线' in changes or not changes else '无改动'
        location = source + (':' + function if function else '')
        kind = '代码生成（修改源函数）' if function or code or source.endswith('.py') else '文本文件（可直接编辑）'
        fence = '`' * max(4, max((len(m[0]) for m in re.finditer(r'`+', text)), default=0)+1)
        start = len('\n'.join(self.parts).splitlines()) + 1
        self.parts.append(f'\n<a id="{anchor}"></a>\n\n### {title}\n\n来源：`{location}`；{kind}；正文 {len(text.encode())} 字节；相对 v2：**{change}**。依赖：{", ".join(dependencies) or "无额外依赖"}。\n\n{note}\n\n{fence}{"python" if code else "text"}\n{text}\n{fence}\n')
        self.fragments.append({'title': title, 'anchor': anchor, 'source': location, 'kind': kind,
                               'bytes': len(text.encode()), 'sha256': digest, 'v2': change,
                               'start_line': start})

    def template(self, title, relative, function):
        self.add(title, source_function(self.root, relative, function), relative, function,
                 note='以下是运行时模板的源函数，动态字段以本次渲染值为例；代码本身不会作为消息发送。', code=True)

    def finish(self):
        body = '\n'.join(self.parts)
        patterns = {word: re.escape(word) for word in ('30 分钟', '先过门', '最佳版本', '收敛', '交叉验证', '本地', 'Job', 'DeepSeek')}
        patterns.update({'内部编号': r'CS-UP(?:-\d+)?|D-\d+',
                         '凭据路径': r'[^\s`"<>]*(?:auth\.json|secrets\.json|\.env|CODEX_HOME|CS_TOOL_TOKEN)[^\s`"<>]*'})
        hits = []
        for line_number, line in enumerate(body.splitlines(), 1):
            for label, pattern in patterns.items():
                for match in re.finditer(pattern, line, re.I):
                    fragment = next((item for item in reversed(self.fragments) if item['start_line'] <= line_number), None)
                    hits.append({'term': label, 'line': line_number, 'column': match.start()+1,
                                 'text': match[0], 'source': fragment['source'] if fragment else '生成说明'})
        lines = ['\n## 疑似冲突扫描与修改落点\n',
                 '扫描对象为以上完整正文（含模板源码、历史交接、元数据）；命中不等同于冲突。旧经验编号、历史昂贵参数和供应商基础内容保留供审阅，不自动改写。下面每条均给出全集行列和原始修改位置。\n',
                 '| 关键词 | 全集行:列 | 命中 | 修改位置 |', '|---|---|---|---|']
        for hit in hits:
            lines.append(f'| {hit["term"]} | {hit["line"]}:{hit["column"]} | {hit["text"].replace("|", "&#124;")} | {hit["source"]} |')
        lines += ['\n## 每段的用户修改落点\n', '| 段落 | 字节 | 相对 v2 | 修改位置 |', '|---|---:|---|---|']
        for item in self.fragments:
            lines.append(f'| [{item["title"]}](#{item["anchor"]}) | {item["bytes"]} | {item["v2"]} | {item["source"]} |')
        return body + '\n'.join(lines), hits


def _handoff(value):
    if isinstance(value, dict):
        if isinstance(value.get('clean_handoff'), dict):
            return value['clean_handoff']
        for child in value.values():
            found = _handoff(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _handoff(child)
            if found:
                return found
    return None


def generate(run_id='run_c726779523'):
    """Only call in a child process: renderers may register temp capabilities/facts."""
    from . import (db, controller, codex_protocol, skills, experience_context,
                  progressive_context, planning, clean_runs, observation,
                  competition_prompts, pi_wake, curation, role_tasks, mcp_bridge)
    from .brains.codex import CodexBrain
    from . import runtime_layout
    root = config.WORKSPACE_ROOT
    baseline = json.loads((Path(__file__).parent / 'prompt_baseline.json').read_text())
    version = runtime_layout.version() or {'commit': 'unpublished-development'}
    with tempfile.TemporaryDirectory(prefix='cs-prompt-render-') as temporary:
        temporary = Path(temporary)
        with sqlite3.connect('file:'+str(config.DB_PATH)+'?mode=ro', uri=True) as original:
            with sqlite3.connect(temporary/'render.db') as copy:
                original.backup(copy)
        shutil.copytree(config.EXPERIENCE_DIR, temporary/'experience')
        original_workspace = config.WORKSPACE_DIR
        config.DB_PATH = temporary/'render.db'
        config.DATA_DIR = temporary
        config.WORKSPACE_DIR = temporary/'workspace'
        config.EXPERIENCE_DIR = temporary/'experience'
        # Current clean-session cwd must refer to the isolated workspace copy.
        db.init_db()
        for event in db.query("SELECT seq,payload FROM events WHERE run_id=? AND type='executor.session_restarted'", (run_id,)):
            db.execute('UPDATE events SET payload=? WHERE run_id=? AND seq=?',
                       (event['payload'].replace(str(original_workspace), str(config.WORKSPACE_DIR)), run_id, event['seq']))
        ctl = controller.RunController()
        run = ctl._require_run(run_id)
        settings = ctl._runtime_settings(run_id)
        challenge = ctl._challenge_for_run(run)
        pi_spec = ctl._brain_spec(run_id, settings, config.WORKSPACE_DIR/'brains'/run_id)
        executor_spec = ctl._prime_spec(run_id, settings)
        def normal(text):
            return text.replace(str(config.WORKSPACE_DIR), str(original_workspace)).replace(str(temporary/'experience'), str(root/'experience'))
        def developer(spec, writable):
            return normal(codex_protocol.thread_params(spec, None, None, writable=writable)['developerInstructions'])
        pi_developer = developer(pi_spec, False)
        executor_developer = developer(executor_spec, True)
        packet = ctl._lifecycle_packet(run, 'run_start')
        pi_first = normal(CodexBrain._render_prompt(packet))
        executor_skills = ctl._enabled_skills(run_id, settings, run['challenge_id'], 'executor')
        brain_skills = ctl._enabled_skills(run_id, settings, run['challenge_id'], 'brain')
        authority = observation.authority_facts(run_id)
        trial = db.query_one('SELECT * FROM trials WHERE id=? AND run_id=?', ('trial_a994721590', run_id))
        if not trial:
            trial = db.query_one('SELECT * FROM trials WHERE run_id=? ORDER BY rowid LIMIT 1', (run_id,))
        if not trial:
            raise ValueError('No real Trial for prompt rendering')
        exploration = progressive_context.executor_prompt(run_id, trial['id'], challenge, trial['goal'],
            trial['success_check'], authority, executor_skills, experience_context.for_trial(run_id, trial['id'])) + planning.brief_for_run(run_id)
        handoff = None
        for event in db.query("SELECT payload FROM events WHERE run_id=? AND payload LIKE '%clean_handoff%' ORDER BY seq DESC", (run_id,)):
            handoff = _handoff(json.loads(event['payload']))
            if handoff:
                break
        if not handoff:
            raise ValueError('No actual clean handoff in RH-02 evidence')
        clean_trial = db.query_one('SELECT * FROM trials WHERE run_id=? ORDER BY rowid DESC LIMIT 1', (run_id,))
        clean_first = clean_runs.prompt(challenge, handoff, executor_skills, authority['capability_summary'],
            run_id=run_id, trial_id=clean_trial['id'], delivery_directory=str(original_workspace/'runs'/run_id/'trials'/clean_trial['id']),
            environment_index={key: authority[key] for key in ('runtime_environments','environment_catalog','environment_choice') if key in authority})
        # Reuse an actual immutable review packet if one was registered.
        review = db.query_one('SELECT packet_json FROM package_reviews WHERE run_id=? ORDER BY rowid DESC LIMIT 1', (run_id,))
        if review:
            review_packet = json.loads(review['packet_json'])
        else:
            # Extract the production literal, rather than maintaining another copy.
            function = ast.parse(source_function(root, 'src/cyberscientist/package_reviews.py', 'review').lstrip())
            instructions = next(ast.literal_eval(v) for node in ast.walk(function) if isinstance(node, ast.Dict)
                                for k,v in zip(node.keys,node.values) if isinstance(k,ast.Constant) and k.value=='instructions')
            review_packet = {'protocol':'role_task','task':'package_review','instructions':instructions,
                'challenge':challenge['content'],'output_contract':__import__('cyberscientist.package_reviews',fromlist=['SCHEMA']).SCHEMA,
                'material_status':'unknown: this export does not seal or create a new review operation'}
        curate_packet = {'protocol':'experience_curation','trigger':'run_curation',
                         'run_evidence':curation.run_evidence(run_id), 'curation':ctl._curation_payload(run)}
        # Production curation adds the current policy decisions, which are also data.
        from . import review_policy
        curate_packet['design_decisions'] = review_policy.decisions()
        active = experience_context.effective(None)
        book = Book(root, baseline)
        book.parts.append('# 提示词全集\n\n由比赛目录实际代码生成。原生记录未修改；模型调用 0；科研计算 0；使用真实 RH-02 题面、Trial、历史交接、当前赛道提示和 active 全局经验。渲染器在只读数据库备份及临时经验副本中运行，避免撤销在用令牌或写入运行事实。临时工作路径在导出后映射回比赛路径。\n\n'
                          + '生成时间：'+db.utcnow()+'；比赛代码 commit：'+version['commit']+'；v2 对照：'+baseline['commit']+'。\n\n'
                          + '注意：干净首条复用 RH-02 当时批准的交接，因此仍能看到历史昂贵设置；这是审阅材料，不代表 v3 自动修改历史方法。事件样例与模板源码均标明；不会伪称已启动会话。供应商内建工具的完整隐藏定义不由应用提供，本书导出全部应用 MCP 定义和线程配置，可见原生系统指令仍以供应商原生记录为准。\n')
        roles = [
            ('PI',pi_developer,pi_first,'src/cyberscientist/controller.py','RunController._brain_spec','src/cyberscientist/brains/codex.py','CodexBrain._render_prompt','brain'),
            ('探索执行者',executor_developer,normal(exploration),'src/cyberscientist/controller.py','RunController._prime_spec','src/cyberscientist/progressive_context.py','executor_prompt','executor'),
            ('干净复跑执行者',executor_developer,normal(clean_first),'src/cyberscientist/controller.py','RunController._prime_spec','src/cyberscientist/clean_runs.py','prompt','executor'),
            ('只读审查者',review_packet['instructions'],normal(role_tasks.prompt(review_packet)),'src/cyberscientist/package_reviews.py','review','src/cyberscientist/role_tasks.py','prompt','reviewer'),
            ('经验整理',pi_developer,normal(curation.prompt(curate_packet)),'src/cyberscientist/controller.py','RunController._brain_spec','src/cyberscientist/curation.py','prompt','curation')]
        for label,dev,first,dev_file,dev_func,first_file,first_func,scope in roles:
            book.parts.append('\n## '+label+'\n')
            book.add('会话级开发者指令',dev,dev_file,dev_func,dependencies=(('prompts/roles/executor.md',) if scope=='executor' else ('prompts/roles/pi.md',) if scope in ('brain','curation') else ()))
            book.add('RH-02 实际渲染首条消息',first,first_file,first_func,
                     dependencies=('prompts/roles/pi.md','templates/lightchaser-user-prompt.md') if scope=='brain' else (),
                     note='运行当前 v3 生成器，不启动原生模型回合；字段来自真实数据库。')
            book.template('首条消息模板',first_file,first_func)
            if scope=='brain':
                for name,value in [('开局轮',{'trigger':'run_start'}),('决策轮',{'trigger':'trial_done'}),
                                   ('审阅轮',{'protocol':'review_result','sparse_brain_version':1}),
                                   ('回答执行者提问',{'protocol':'executor_question','sparse_brain_version':1})]:
                    # Identical real evidence; only protocol discriminator changes.
                    book.add(name+'模板渲染',normal(CodexBrain._render_prompt({**packet,**value})),
                             'src/cyberscientist/brains/codex.py','CodexBrain._render_prompt',dependencies=('prompts/collaboration/brain.md',),
                             note='使用真实题面和当前帧数据展示协议模板；不是新决策或模型回答。')
                book.template('事件唤醒文字：计算、交付、定时及复核','src/cyberscientist/pi_wake.py','collect')
                book.add('当前真实节奏信息',json.dumps(pi_wake.cadence(run_id),ensure_ascii=False,indent=2),'src/cyberscientist/pi_wake.py','cadence')
            elif scope=='executor':
                book.template('每轮继续与指导送达模板','src/cyberscientist/controller.py','RunController._deliver_queued_guidance')
                book.parts.append('\n事件唤醒送给 PI；执行者不接收监控指导或复核开发内容。执行者当前回合由指导和检查点回执推进。\n')
            else:
                book.parts.append('\n此角色是一项有界请求，无独立循环轮或计算唤醒。经验整理实际继承 PI 开发者指令，而首条又要求不用工具；这里如实呈现供审阅。\n')
                if scope=='reviewer':
                    book.template('审查材料、审计补充和开发者指令模板','src/cyberscientist/package_reviews.py','review')
            book.template('指导送达与 ACK 格式','src/cyberscientist/collab.py','deliver_via_checkpoint_return')
            names = codex_protocol.COLLAB_TOOLS if scope=='executor' else codex_protocol.BRAIN_TOOLS if scope in ('brain','curation') else ()
            book.add('工具清单及说明',json.dumps([tool for tool in [*mcp_bridge._TOOLS,mcp_bridge._FILES_TOOL,mcp_bridge._VARIANT_TOOL,mcp_bridge._REVIEW_TOOL,mcp_bridge._TRACE_TOOL,mcp_bridge._SCORES_TOOL] if tool['name'] in names and not (tool['name']=='research_trace_narrative_check' and settings.get('evidence_mode')=='competition')],ensure_ascii=False,indent=2),'src/cyberscientist/mcp_bridge.py',dependencies=('src/cyberscientist/codex_protocol.py',),code=False,
                     note='应用工具定义；审查者没有应用 MCP。经验整理首条要求不用工具，线程仍由 PI 规格创建。')
            role_skills = executor_skills if scope=='executor' else brain_skills if scope in ('brain','curation') else []
            book.add('技能索引（全部正文见共用附录）',normal(skills.prompt_segment(role_skills)), 'src/cyberscientist/skills.py','prompt_segment')
            visible = [x for x in active if x.get('audience','both') in ('both','executor' if scope=='executor' else 'brain')]
            book.add('active 全局经验索引（全部正文见共用附录）',json.dumps(experience_context.index(None,entries=visible if scope!='reviewer' else []),ensure_ascii=False,indent=2),'src/cyberscientist/experience_context.py','index',note='索引是当前可读取集合；首条的冻结/预算裁剪内容以上实际渲染为准。只读审查者不访问经验。')
            book.add('赛道用户提示（PI 接收，其余通过 PI 任务派发）',json.dumps(competition_prompts.packet(run),ensure_ascii=False,indent=2), 'src/cyberscientist/competition_prompts.py','packet',dependencies=('templates/lightchaser-user-prompt.md',))
        book.parts.append('\n## 共用附录：全部启用技能正文\n\n每个角色索引所指的正文均在此完整收录，不重复复制。\n')
        all_skills = {item['id']:item for item in [*brain_skills,*executor_skills]}
        for identifier,item in sorted(all_skills.items()):
            path=Path(item['source'])/identifier/'SKILL.md'
            book.add('技能 '+identifier,path.read_text(),str(path.relative_to(root)))
        book.parts.append('\n## 共用附录：全部 active 全局经验正文\n')
        for item in active:
            source=db.query_one('SELECT file_path FROM experience_revisions WHERE id=?',(item['revision_id'],))
            path=str(source['file_path']) if source else 'experience/global/'+item['id']+'.md'
            if not path.startswith('experience/'):
                path='experience/'+path
            book.add('全局经验 '+item['id'],item['full_content'],path,note='实际 active 修订 '+item['revision_id']+'；SHA256 '+item['revision_hash']+'。修改后全局候选仍须前端审批。')
        markdown,hits=book.finish()
        # Exact stored secrets, including encoded forms, must never enter Git.
        from . import native_logs
        if any(item.get('exact_stored') for item in native_logs.secret_findings(json.dumps({'export':markdown}))):
            raise ValueError('Prompt export contains a stored credential; export refused')
        return {'markdown':markdown,'metadata':{'run_id':run_id,'runtime_version':version,'baseline':baseline['commit'],
            'fragments':book.fragments,'scan_hits':hits,'enabled_skills':sorted(all_skills),'active_global_experiences':len(active),
            'model_turns':0,'pi_first_bytes':len(pi_first.encode()),'pi_v3_scoring_delivered':all(s in pi_developer for s in ('评分在查什么','第一版直接用，不做收敛扫描','不换成探索中试过的更贵设置'))}}


def dump(run_id='run_c726779523'):
    """Invoke the installed competition generator, keeping server config immutable."""
    result=subprocess.run([sys.executable,'-m','cyberscientist.prompt_book',run_id],cwd=config.WORKSPACE_ROOT,
                          capture_output=True,text=True,timeout=180,check=False)
    if result.returncode:
        from . import observation
        raise ValueError(observation.strip_secrets(result.stderr[-2500:]))
    return json.loads(result.stdout)


if __name__=='__main__':
    print(json.dumps(generate(sys.argv[1] if len(sys.argv)>1 else 'run_c726779523'),ensure_ascii=False))
