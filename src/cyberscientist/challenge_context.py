"""Model-facing metadata projection; raw imported records remain unchanged."""
from copy import deepcopy
import json

SCORING_FACT = '实际科学分由平台用题目的隐藏测试评定（harbor）；严格按题面的输出契约交付。'


def platform(value):
    if not isinstance(value,dict):return deepcopy(value)
    result=deepcopy(value)
    if 'scoring' in result:
        result.pop('scoring')
        result['science_scoring_fact']=SCORING_FACT
    for wrapper in ('challenge','data'):
        if isinstance(result.get(wrapper),dict):result[wrapper]=platform(result[wrapper])
    return result


def project(value):
    if isinstance(value,list):return [project(item) for item in value]
    if not isinstance(value,dict):return deepcopy(value)
    result={}
    for key,item in value.items():
        if key in ('platform','platform_snapshot'):
            result[key]=platform(item)
        elif key=='platform_snapshot_json' and isinstance(item,str):
            result[key]=json.dumps(platform(json.loads(item or 'null')),ensure_ascii=False)
        else:result[key]=project(item)
    return result
