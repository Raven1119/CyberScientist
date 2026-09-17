"""Validate this design package and its offline HTML prototype.
Not a backend, not a live integration test. Browser storage uses an explicit
in-memory test double because the authoring browser blocks local navigation.
Install dependencies separately; never calls external model/platform APIs.
"""
from pathlib import Path
import json, re, yaml, copy, os, shutil
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.package-checks';OUT.mkdir(exist_ok=True)
results=[]
def check(name, fn):
 fn();results.append({'check':name,'status':'pass'})
cfg=yaml.safe_load((ROOT/'config/workspace.example.yaml').read_text())
cs=json.loads((ROOT/'contracts/config.schema.json').read_text())
ds=json.loads((ROOT/'contracts/decision.schema.json').read_text())
de=json.loads((ROOT/'config/decision.example.json').read_text())
check('config schema self-validation', lambda: Draft202012Validator.check_schema(cs))
check('decision schema self-validation', lambda: Draft202012Validator.check_schema(ds))
cv=Draft202012Validator(cs,format_checker=FormatChecker())
dv=Draft202012Validator(ds,format_checker=FormatChecker())
check('YAML configuration sample validates',lambda: cv.validate(cfg))
check('decision sample validates',lambda: dv.validate(de))
def reject(v,obj):
 try:v.validate(obj)
 except ValidationError:return
 raise AssertionError('Invalid fixture unexpectedly accepted')
bad=copy.deepcopy(cfg);bad['prime']['automatic_refine']=True
check('configuration rejects automatic refine in v0.1',lambda: reject(cv,bad))
bad2=copy.deepcopy(de);bad2['actions']=[{'op':'steer','message':'missing trial'}]
check('decision rejects incomplete steer action',lambda: reject(dv,bad2))
bad3=copy.deepcopy(de);bad3['experience_proposals']=[{'scope':'global','challenge_id':'not-null','title':'x','body_md':'x','applicability':'x','evidence_refs':[]}]
check('decision rejects global proposal with challenge identity',lambda: reject(dv,bad3))
fm=(ROOT/'templates/experience.md').read_text().split('---',2)[1]
check('experience template YAML parses',lambda: yaml.safe_load(fm))
# Validate links that are intended to exist in this delivery, excluding planned files in code spans.
missing=[]
for f in ROOT.rglob('*.md'):
 for match in re.finditer(r'\]\(([^)]+)\)',f.read_text()):
  target=match.group(1)
  if '://' not in target and not target.startswith('#'):
   if not (f.parent/target.split('#')[0]).exists():missing.append((str(f),target))
check('local Markdown links resolve',lambda: (_ for _ in ()).throw(AssertionError(missing)) if missing else None)
with sync_playwright() as p:
 launch={'headless':True}
 executable=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('google-chrome')
 if executable: launch['executable_path']=executable
 if hasattr(os,'geteuid') and os.geteuid()==0: launch['args']=['--no-sandbox']
 browser=p.chromium.launch(**launch)
 ctx=browser.new_context(viewport={'width':1440,'height':1100},device_scale_factor=1)
 page=ctx.new_page();errors=[];external=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda req:external.append(req.url))
 # Managed Chromium blocks local URL navigation. Render generated HTML directly;
 # use an explicitly labelled in-memory Storage test double for persistence logic.
 storage_js = '''(seed) => { class TestStorage { constructor(seed) { this.data = seed || {}; } getItem(k) { return Object.prototype.hasOwnProperty.call(this.data,k) ? this.data[k] : null; } setItem(k,v) { this.data[k] = String(v); } removeItem(k) { delete this.data[k]; } clear() { this.data = {}; } } Object.defineProperty(window, 'localStorage', {value: new TestStorage(seed), configurable: true}); }'''
 page.evaluate(storage_js,{})
 page.set_content((ROOT/'prototype/index.html').read_text(),wait_until='load')
 assert '交互原型' in page.locator('.badge.demo').first.inner_text()
 assert page.locator('#run-status').inner_text()=='等待开始（模拟）'
 results.append({'check':'initial screen explicitly labels demo and no real score','status':'pass'})
 page.locator('#start-btn').click();page.locator('#advance-btn').click()
 assert page.locator('#snapshot-summary').inner_text().endswith('@ v1')
 page.locator('#pause-btn').click();assert '已暂停' in page.locator('#run-status').inner_text()
 page.locator('#start-btn').click();assert '进行中' in page.locator('#run-status').inner_text()
 results.append({'check':'start, advance, pause and resume simulation','status':'pass'})
 page.locator('#steer-btn').click();page.locator('#steer-message').fill('TEST: 先核对评分反馈 <img src="https://invalid.example/x">')
 page.locator('#send-steer-btn').click();assert '已排队' in page.locator('#events').inner_text()
 page.locator('#advance-btn').click();assert '模拟指导消费' in page.locator('#events').inner_text()
 assert page.locator('#events img').count()==0
 results.append({'check':'guidance queue and safe text rendering','status':'pass'})
 page.screenshot(path=str(OUT/'research-desktop.png'),full_page=True)
 page.locator('[data-view="experience"]').click()
 old=page.locator('#exp-body').input_value()
 page.locator('#exp-body').fill(old+'\n\nTEST: 新的待验证观察。')
 page.locator('#save-exp-btn').click();assert 'v2' in page.locator('#revision-badge').inner_text()
 page.locator('#history-btn').click();assert 'TEST:' in page.locator('#history-after').inner_text()
 page.locator('#restore-btn').click();assert 'v3' in page.locator('#revision-badge').inner_text()
 assert page.locator('#exp-body').input_value()==old
 results.append({'check':'Markdown edit, immutable revisions and restore-as-new-revision','status':'pass'})
 page.screenshot(path=str(OUT/'experience-desktop.png'),full_page=True)
 page.locator('[data-view="research"]').click();assert page.locator('#snapshot-summary').inner_text().endswith('@ v1')
 results.append({'check':'running memory snapshot survives experience edits','status':'pass'})
 page.locator('[data-view="settings"]').click()
 page.locator('#brain-runtime').select_option('kimi')
 page.locator('#llm-model').fill('DEMO_MODEL_ID')
 page.locator('#llm-base').fill('https://provider.example/v1')
 for ident in ['prime-key','playground-key','bohr-key']:page.locator('#'+ident).fill('TEST_SECRET_'+ident)
 page.locator('#save-settings-btn').click()
 stored=page.evaluate('JSON.stringify(localStorage)')
 assert 'TEST_SECRET' not in stored
 for ident in ['prime-key','playground-key','bohr-key']:assert page.locator('#'+ident).input_value()==''
 results.append({'check':'secrets cleared and excluded from browser storage','status':'pass'})
 page.locator('[data-view="research"]').click();assert page.locator('#brain-summary').inner_text().startswith('Codex')
 results.append({'check':'active run retains original brain selection after settings change','status':'pass'})
 seed=page.evaluate('localStorage.data')
 page.close();page=ctx.new_page()
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda req:external.append(req.url))
 page.evaluate(storage_js,seed)
 page.set_content((ROOT/'prototype/index.html').read_text(),wait_until='load')
 page.locator('[data-view="settings"]').click();assert page.locator('#brain-runtime').input_value()=='kimi';assert page.locator('#llm-model').input_value()=='DEMO_MODEL_ID'
 page.locator('[data-view="experience"]').click();assert 'v3' in page.locator('#revision-badge').inner_text()
 results.append({'check':'nonsecret configuration and revisions restore using explicit in-memory Storage fixture','status':'pass'})
 page.locator('[data-view="settings"]').click();page.locator('#reset-btn').click()
 page.locator('#inspect-btn').click();assert '不能检查' in page.locator('#toast').inner_text()
 results.append({'check':'connection check never claims an actual connection','status':'pass'})
 page.locator('[data-view="research"]').click()
 page.evaluate("document.getElementById('toast').hidden = true")
 page.screenshot(path=str(OUT/'research-clean.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844})
 for view in ['research','experience','settings']:
  page.locator('[data-view="'+view+'"]').click()
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), f'overflow: {view}'
  page.screenshot(path=str(OUT/(view+'-mobile.png')),full_page=True)
 results.append({'check':'three pages have no document-level horizontal overflow at 390px','status':'pass'})
 assert not errors, errors
 results.append({'check':'browser reports no uncaught JavaScript errors','status':'pass'})
 assert not external, external
 results.append({'check':'no external network requests during prototype interaction','status':'pass'})
 # Verify graceful fallback without any accessible browser storage.
 filepage=ctx.new_page()
 filepage.set_content((ROOT/'prototype/index.html').read_text(),wait_until='load')
 filepage.locator('[data-view="experience"]').click()
 assert filepage.locator('#exp-body').is_visible()
 filepage.locator('#exp-body').fill('Storage fallback test')
 filepage.locator('#save-exp-btn').click()
 assert '存储不可用' in filepage.locator('#toast').inner_text()
 results.append({'check':'prototype remains usable when browser storage is unavailable','status':'pass'})
 browser.close()
(OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
print(json.dumps({'checks_passed':len(results),'results':results},indent=2,ensure_ascii=False))
