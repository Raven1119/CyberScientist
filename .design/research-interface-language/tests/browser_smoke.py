#!/usr/bin/env python3
"""Optional real-browser smoke checks (not needed to use/install the kit).

Requires Python playwright and a Chromium executable or Playwright browser install.
  python tests/browser_smoke.py --chromium /path/to/chromium
  python tests/browser_smoke.py --in-memory --chromium /path/to/chromium

Default: temporary loopback HTTP server. --in-memory uses set_content where browser
policy blocks URLs; localStorage persistence cannot be tested in that opaque origin.
Shaders without a WebGL context are reported UNSUPPORTED, not falsely passed.
"""
from pathlib import Path
import argparse
import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium')
    parser.add_argument('--in-memory', action='store_true')
    parser.add_argument('--screenshots', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit('Optional test needs playwright. Install in a test environment; it is not an application dependency.')
    server = None
    base = ''
    if not args.in_memory:
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *_): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(server.server_port)
    result = {'mode': 'in-memory' if args.in_memory else 'loopback-http', 'passed': [], 'unsupported': [], 'errors': []}
    def load(page, relative):
        if args.in_memory:
            path = ROOT / relative
            content = path.read_text(encoding='utf-8')
            def css(match):
                target = path.parent / match.group(1)
                return '<style>' + target.read_text(encoding='utf-8') + '</style>'
            content = re.sub(r'<link rel="stylesheet" href="([^"]+)"\s*/?>', css, content)
            page.set_content(content, wait_until='domcontentloaded')
        else:
            page.goto(base + '/' + relative)
        page.wait_for_timeout(1000)
    def passed(label): result['passed'].append(label)
    def shot(page, filename, full=False):
        if args.screenshots:
            args.screenshots.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshots / filename), full_page=full)
    try:
        with sync_playwright() as p:
            launch = {'headless': True, 'args': ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader']}
            if args.chromium: launch['executable_path'] = args.chromium
            browser = p.chromium.launch(**launch)
            result['browser'] = browser.version
            ctx = browser.new_context(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
            page = ctx.new_page(); page.on('pageerror', lambda e: result['errors'].append(str(e)))
            load(page, 'assets/reference.html')
            assert page.evaluate('ResearchDemo.state.version') == 9
            passed('Frozen reference application initializes')
            for mode in ['dithering', 'metaballs', 'threads', 'particles', 'interactive', 'dots']:
                page.evaluate('(m)=>ResearchDemo.chooseField(m)', mode)
                page.wait_for_timeout(760)
                scenes = page.evaluate('ResearchMotion.state.scenes')
                if scenes:
                    assert len(scenes) == 1 and scenes[0]['mode'] == mode
                    if mode != 'dots':
                        old = scenes[0]['frames']; page.wait_for_timeout(180)
                        assert page.evaluate('ResearchMotion.state.scenes[0].frames') > old
                    passed('Scene renders: ' + mode)
                else:
                    assert page.locator('#obs-aperture .error-box').count() == 1
                    result['unsupported'].append('WebGL scene unavailable in this browser: ' + mode)
            assert page.evaluate('ResearchMotion.state.scenes.length') == 1
            before = page.evaluate('ResearchMotion.state.scenes[0].frames')
            aperture = page.locator('#obs-aperture').bounding_box()
            page.mouse.click(aperture['x']+aperture['width']/2, aperture['y']+aperture['height']/2)
            page.wait_for_timeout(200)
            assert page.evaluate('ResearchMotion.state.scenes[0].frames') > before
            passed('Dot-grid interaction changes rendered frames')
            page.mouse.move(20, 200); page.wait_for_timeout(1800)
            shot(page, 'workspace-paper.png')
            page.click('#theme-toggle'); page.wait_for_timeout(250)
            assert page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim().toLowerCase()") == '#17191a'
            shot(page, 'workspace-night.png'); passed('Exact cool-graphite night CSS tokens')
            page.click('#focus-toggle'); page.wait_for_timeout(300); shot(page, 'workspace-focus.png')
            assert page.locator('body').evaluate("e=>e.classList.contains('attention-mode')")
            page.click('#focus-toggle'); passed('Focus mode enter/exit')
            # Actual pixel primitive: cover occurs before one swap, overlay is removed.
            page.evaluate("""()=>{window.__swapCount=0;ResearchMotion.pixelTransition(document.getElementById('obs-aperture'),()=>window.__swapCount++);} """)
            page.wait_for_timeout(140)
            assert page.locator('.source-pixel-grid').count() == 1
            assert page.evaluate('window.__swapCount') == 0
            assert page.locator('.source-pixel-grid i:visible').count() > 0
            page.wait_for_timeout(700)
            assert page.evaluate('window.__swapCount') == 1
            assert page.locator('.source-pixel-grid').count() == 0
            passed('Pixel cover -> one swap -> reveal/cleanup')
            for _ in range(10):
                page.evaluate("ResearchDemo.mountField('dots')")
            page.wait_for_timeout(200)
            assert page.evaluate('ResearchMotion.state.scenes.length') == 1
            assert page.locator('#obs-aperture canvas').count() == 1
            passed('Ten scene replacements retain one canvas and one live scene')
            page.locator('#note').fill('打包验收：保留正文与草稿。')
            assert page.evaluate('ResearchMotion.state.writing')
            count = page.evaluate('ResearchMotion.state.scenes[0].frames')
            page.wait_for_timeout(200)
            assert page.evaluate('ResearchMotion.state.scenes[0].frames') == count
            passed('Writing stops scene frame updates')
            page.locator('#note-form button[type=submit]').click()
            assert page.locator('#note').input_value() == '打包验收：保留正文与草稿。'
            assert page.evaluate('ResearchDemo.state.records') >= 1
            passed('Record submission retains editor text')
            if not page.evaluate('ResearchDemo.state.storageOK'):
                result['unsupported'].append('Persistent localStorage unavailable at the test origin; fallback only tested')
            # Restore a clean sample before mobile reference capture.
            page.evaluate("ResearchDemo.selectTask('R-023')")
            page.wait_for_timeout(1100)
            page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(400)
            assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
            shot(page, 'workspace-mobile.png', True);passed('390px viewport: no horizontal overflow')
            page.set_viewport_size({'width':1440,'height':1100})
            # Wizard through actual UI.
            page.locator('[data-new]').first.click();page.wait_for_timeout(200)
            page.fill('#new-title','新建研究验收');page.click('#wizard-next');page.wait_for_timeout(800)
            page.fill('#new-question','主工作流能否正常完成？');page.click('#wizard-next');page.wait_for_timeout(800)
            page.click('#wizard-next');page.wait_for_timeout(1300)
            assert page.locator('#task-heading').inner_text() == '新建研究验收'
            assert not page.locator('#new-dialog').evaluate('e=>e.open')
            passed('Actual three-step wizard creates a task')
            # Reduced motion is a separate page/context, not a visual simulation.
            reduced = browser.new_context(reduced_motion='reduce',viewport={'width':1440,'height':1000})
            pr = reduced.new_page();pr.on('pageerror', lambda e: result['errors'].append(str(e)))
            load(pr,'assets/reference.html')
            assert not pr.evaluate('ResearchMotion.canMove()')
            pr.evaluate("()=>{window.__swapCount=0;ResearchMotion.pixelTransition(document.getElementById('obs-aperture'),()=>window.__swapCount++);}")
            assert pr.evaluate('window.__swapCount') == 1 and pr.locator('.source-pixel-grid').count() == 0
            passed('Reduced-motion preference skips pixel motion but commits state')
            pr.close();reduced.close()
            starter = ctx.new_page();starter.on('pageerror',lambda e: result['errors'].append(str(e)))
            load(starter,'examples/starter.html'); shot(starter,'starter.png')
            starter.fill('#note','起步页验收');starter.click('#save')
            assert starter.locator('#note').input_value() == '起步页验收'
            starter.click('#theme')
            assert starter.evaluate("document.documentElement.dataset.theme") == 'night'
            passed('Standalone starter: editor, save feedback and theme toggle')
            browser.close()
        assert not result['errors'], result['errors']
        passed('No uncaught page JavaScript exceptions in executed paths')
    finally:
        if server: server.shutdown()
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__ == '__main__': main()
