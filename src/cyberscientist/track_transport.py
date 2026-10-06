"""A track's observed, explicitly reviewed ARM transport, frozen for each Run."""
from __future__ import annotations
import copy
import json
import re
from . import config, db, observation, platform_contracts
from .mailbox_platform import BohriumPlaygroundPlatform, PlatformError

PATHS = {
    'create': ('POST', '/challenges/{id}/attempts'),
    'bundle': ('POST', '/attempts/{id}/bundle'),
    'submit': ('POST', '/attempts/{id}/submit'),
    'attempt': ('GET', '/attempts/{id}'),
    'score': ('GET', '/attempts/{id}/score'),
}


def defaults(base=None):
    base=base or config.load_settings()['playground']['base_url']
    return {'base_url':base.rstrip('/'),'paths':{k:v[1] for k,v in PATHS.items()},
            'bundle_format':'arm_zip_multipart','bundle_field':'bundle','protocol_version':'1.1',
            'topic_link':platform_contracts._origin(base)+'/challenges/{id}'}


def probe(mode,snapshot=None):
    base=defaults();result=base | {'verified':False,'status':'unknown','evidence':{}}
    if snapshot:
        result['track_identity']={'season':snapshot.get('season'),'round_seq':snapshot.get('round_seq'),
                                  'challenge_ids':[e['challenge_id'] for e in snapshot.get('entries',[])]}
    if mode=='demo': return result | {'status':'demo','verified':True}
    from . import protocol_drift
    try:
        protocol,pm=protocol_drift._read_public('track_protocol','/api/protocol',base['base_url'],json_document=True)
        document,dm=protocol_drift._read_public('track_agent_api','/api/docs/dev/AGENT_API.md',base['base_url'],json_document=False)
        result['evidence']={'protocol':pm,'agent_api':dm}
        # Only recognize the documented transport, never guess new fields.
        paths_ok=all(re.search(re.escape(path).replace(r'\{id\}',r'\{[^}]+\}'),document)
                     for name,(_,path) in PATHS.items() if name in ('create','bundle','submit'))
        defaults_observed=bool(isinstance(protocol,dict) and '1.1' in protocol.get('accepted_versions',[]) and paths_ok)
        result['status']='platform_defaults_observed_needs_track_review' if defaults_observed else 'needs_review'
        result['evidence']['default_transport_documented']=defaults_observed
        result['scope']='platform_global_docs; track_specific_rules_require_review_if_different'
    except Exception as exc:
        result['reason']=observation.strip_secrets(str(exc))[:300]
    return result


def validate(value, *, base_url=None):
    if not isinstance(value,dict): raise ValueError('赛道提交配置须为对象')
    allowed=set(defaults()) | {'verified','status','evidence','scope','reason','reviewed_at','track_identity'}
    if set(value)-allowed: raise ValueError('赛道提交配置字段不符')
    result=defaults(base_url) | value
    if platform_contracts._origin(result['base_url'])!=platform_contracts._origin(base_url or defaults()['base_url']):
        raise ValueError('提交端点必须位于已配置平台，不能把凭据发送到其他平台')
    if result['base_url'].rstrip('/')!=(base_url or defaults()['base_url']).rstrip('/'):
        raise ValueError('提交平台根路径必须与已配置平台相同')
    paths=result['paths']
    if not isinstance(paths,dict) or set(paths)!=set(PATHS): raise ValueError('提交端点须包含create/bundle/submit/attempt/score')
    for path in paths.values():
        if not isinstance(path,str) or path.count('{id}')!=1 or not re.fullmatch(r'/[A-Za-z0-9_./{}-]+',path) or '..' in path or re.sub(r'\{id\}','',path).count('{'):
            raise ValueError('提交端点须为相对路径，并只包含一个{id}占位符')
    if result['bundle_format']!='arm_zip_multipart' or result['protocol_version'] not in ('1.0','1.1'):
        raise ValueError('此赛道提交协议尚未适配；请保留未验证状态')
    if not isinstance(result['bundle_field'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',result['bundle_field']): raise ValueError('bundle字段无效')
    link=result['topic_link']
    if not isinstance(link,str) or link.count('{id}')!=1 or platform_contracts._origin(link)!=platform_contracts._origin(result['base_url']): raise ValueError('题目链接必须属于本平台且包含{id}')
    if observation.strip_secrets(json.dumps(result,ensure_ascii=False))!=json.dumps(result,ensure_ascii=False): raise ValueError('赛道提交配置不能含密钥')
    if type(result.get('verified',False)) is not bool: raise ValueError('协议核对标记须为布尔值')
    return copy.deepcopy(result)


def for_run(run_id):
    row=db.query_one('SELECT config_snapshot FROM runs WHERE id=?',(run_id,))
    return json.loads(row[0]).get('competition',{}).get('submission_transport') if row else None


class TrackPlatform(BohriumPlaygroundPlatform):
    def __init__(self,transport,original):
        # Frozen origin remains authoritative if settings later change.
        if original.base_url.rstrip('/')!=transport['base_url'].rstrip('/'):
            raise PlatformError('冻结赛道与当前凭据的平台地址不同，不能确认邮箱归属；未发送',no_side_effect=True)
        self.transport=validate(transport,base_url=transport['base_url'])
        if self.transport.get('verified') is not True: raise PlatformError('赛道提交协议尚未核对，未发送',no_side_effect=True)
        super().__init__(self.transport['base_url'],operator_token=original.operator_token,timeout=original.timeout,framework=original.framework)

    def submit_package(self,email,secret,package_path,challenge_id='',meta=None):
        import io,zipfile
        from pathlib import Path
        package=Path(package_path)
        if package.suffix.lower()=='.zip':
            try:
                raw=(meta or {}).get('package_bytes')
                raw=package.read_bytes() if raw is None else raw
                with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                    names=[n for n in bundle.namelist() if n=='arm_manifest.json' or n.endswith('/arm_manifest.json')]
                    if len(names)!=1: raise ValueError('manifest须有唯一目录根')
                    if bundle.getinfo(names[0]).file_size>2_000_000: raise ValueError('manifest过大')
                    manifest=json.loads(bundle.read(names[0]))
                if manifest.get('arm_version')!=self.transport['protocol_version']:
                    raise PlatformError('封存包版本与本赛道协议版本不同，未发送',no_side_effect=True)
            except (ValueError,OSError,KeyError,zipfile.BadZipFile) as exc:
                raise PlatformError('无法核对本赛道ARM版本，未发送',no_side_effect=True) from exc
        return super().submit_package(email,secret,package_path,challenge_id,meta)

    def _open_http(self,request,*,timeout):
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        # A credentials-bearing API request must not follow even a same-site redirect.
        return urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout)

    def _http(self,method,path,**kwargs):
        for name,(verb,canonical) in PATHS.items():
            if verb!=method: continue
            match=re.fullmatch(re.escape(canonical).replace(r'\{id\}',r'([^/]+)'),path)
            if match:
                path=self.transport['paths'][name].format(id=match[1])
                if name=='bundle' and kwargs.get('form'):
                    fields,files=kwargs['form']
                    kwargs['form']=(fields,[(self.transport['bundle_field'] if field=='bundle' else field,filename,data) for field,filename,data in files])
                break
        return super()._http(method,path,**kwargs)


def bind(platform,run_id):
    transport=for_run(run_id)
    return TrackPlatform(transport,platform) if transport and isinstance(platform,BohriumPlaygroundPlatform) else platform
