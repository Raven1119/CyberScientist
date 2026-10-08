import json,base64
import pytest
from cyberscientist import config,db,progressive_context as pc,pi_files,planning
from cyberscientist.controller import RunController
from test_mailboxes import _seed_challenge,_make_run


def seed():
    settings=config.load_settings();settings['progressive_context']=True;config.save_settings(settings)
    _seed_challenge();return _make_run()


def test_progressive_packet_retains_statement_and_versioned_full_facts():
    rid=seed();statement='题面全部科学约束'*500
    entry={'id':'experience','title':'相关经验','body_md':'完整经验正文'*300,'revision_id':'revision','revision_hash':'hash','applicability':'范围'}
    packet={'challenge':{'content':statement},'round_challenge_snapshot':{'content':statement},'run_objective':statement+'\n用户附加约束必须保留','experience_manifest':[entry],'experience_index':[entry]*20,'operating_facts':{'remaining':{'jobs':1},'details':'不可丢失的完整事实'*500},'feedback':{'goal_md':statement,'round_challenge_snapshot':{'content':statement},'operating_facts':{'x':'duplicated'},'experiences':[entry]},'research_startup':{'problem_md':statement,'strategy_cards':[entry],'brief_fields':[]}}
    out=pc.compact(rid,packet)
    assert out['challenge']['content']==statement and '用户附加约束必须保留' in out['run_objective']
    assert 'body_md' not in out['experience_manifest'][0]
    assert 'body_md' not in out['research_startup']['strategy_cards'][0]
    assert pc.measure(out)['total_bytes'] < pc.measure(packet)['total_bytes']/4
    source=out['progressive_disclosure']['source'];first=pi_files.access(rid,{'action':'read','scope':'facts','path':source['path']})
    assert first['sha256']==source['sha256']
    decode=lambda page:base64.b64decode(page['content']) if page['encoding']=='base64' else page['content'].encode()
    pages=[decode(first)]
    while first['next_offset'] is not None:
        first=pi_files.access(rid,{'action':'read','scope':'facts','path':source['path'],'offset':first['next_offset'],'expected_sha256':source['sha256']});pages.append(decode(first))
    assert json.loads(b''.join(pages))==packet


def test_required_selected_capabilities_and_backend_preserves_legacy_fixture_switch():
    rid=seed();assert pc.enabled(rid)
    with pytest.raises(ValueError,match='selected_capabilities'):planning.record_brief(rid,{'problem_md':'方法'},'missing')
    event=planning.record_brief(rid,{'selected_capabilities':['bohrium-job'],'environment_choice':{'mode':'from_zero','reason_md':'测试'}},'complete')
    assert event


def test_experience_index_top_n_is_bounded_and_no_full_body():
    values=[{'id':str(n),'title':'标题','body_md':'long '*1000} for n in range(100)]
    out=pc.experience_index(values)
    assert len(out)==8 and all(len(row['summary'])<=160 and 'body_md' not in row for row in out)


def test_facts_cannot_escape_run(tmp_path):
    rid=seed();root=config.WORKSPACE_DIR/'runs'/rid;root.mkdir(parents=True,exist_ok=True)
    (root/'facts').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError,match='事实目录'):pc.compact(rid,{'challenge':{}})
