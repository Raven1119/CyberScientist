"""Additional presentation checks against an isolated native Demo workspace.

Uses the real API; CDP latency delays actual responses to inspect loading UI.
No endpoint is replaced with fixture data. Invoke with a Playwright Python env.
"""
from pathlib import Path
import argparse
import json

from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    parser.add_argument('--output', type=Path, default=Path('checks/shots/design-language'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport={'width': 1440, 'height': 1100}, locale='zh-CN')
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        health = context.request.get(args.url + '/api/v1/health')
        assert health.headers.get('x-cyberscientist-ui-demo') == 'isolated-native-demo'
        assert health.json()['mode'] == 'demo'
        page.goto(args.url)
        expect(page.get_by_role('heading', name='研究工作台', exact=True)).to_be_visible()
        page.wait_for_timeout(800)
        expect(page.locator('.challenge-title')).to_be_visible()  # ui_design_smoke imports the Demo challenge.

        def record(name, **details):
            checks.append({'check': name, 'passed': True, **details})

        def shot(name):
            page.screenshot(path=str(args.output / (name + '.png')))

        def frames():
            return int(page.locator('.observation-canvas').get_attribute('data-frames'))

        page.get_by_role('button', name='02 点阵').click()
        page.wait_for_timeout(140)
        count = page.locator('.source-pixel-grid i').evaluate_all(
            "xs=>xs.filter(x=>getComputedStyle(x).display==='block').length")
        assert 0 < count < 144, count
        page.locator('.observation-aperture').screenshot(path=str(args.output / '11-pixel-cover.png'))
        page.wait_for_timeout(650)
        expect(page.locator('.observation-aperture')).to_have_attribute('data-mode', 'dots')
        page.locator('.observation-aperture').screenshot(path=str(args.output / '12-pixel-revealed.png'))
        record('opaque pixel cover and reveal', covered_tiles=count)
        page.evaluate("""()=>{const [a,b]=document.querySelectorAll('.observation-modes button');
            a.click();b.click();a.click();}""")
        page.wait_for_timeout(720)
        expect(page.locator('.observation-aperture')).to_have_attribute('data-mode', 'threads')
        assert page.locator('.source-pixel-grid').count() == 0
        assert page.locator('.observation-canvas').count() == 1
        record('rapid pixel switching keeps newest selection and one canvas')

        button = page.get_by_role('button', name='导入题目', exact=True).first
        button.focus()
        page.keyboard.press('Enter')
        dialog = page.locator('dialog[open]')
        expect(dialog).to_be_visible()
        assert dialog.evaluate('d=>d.contains(document.activeElement)')
        page.keyboard.press('Escape')
        expect(dialog).not_to_be_visible()
        expect(button).to_be_focused()
        record('keyboard dialog focus and Escape restoration')

        cdp = context.new_cdp_session(page)
        cdp.send('Network.enable')
        cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 1800,
                  'downloadThroughput': -1, 'uploadThroughput': -1})
        page.get_by_role('navigation', name='主导航').get_by_role('button', name='连接与设置').click()
        expect(page.locator('.loading-state').filter(has_text='正在加载设置')).to_be_visible()
        shot('13-loading')
        expect(page.get_by_role('heading', name='连接与设置', exact=True)).to_be_visible()
        cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 0,
                  'downloadThroughput': -1, 'uploadThroughput': -1})
        record('loading UI under actual network latency')
        page.get_by_role('navigation', name='主导航').get_by_role('button', name='研究工作台').click()
        page.wait_for_timeout(700)
        page.get_by_role('button', name='切换夜间主题').hover()
        page.wait_for_timeout(220)
        expect(page.locator('.target-cursor')).to_have_attribute('data-active', 'true')
        assert page.get_by_role('button', name='切换夜间主题').evaluate('e=>getComputedStyle(e).cursor') != 'none'
        record('target cursor keeps native pointer')

        page.get_by_role('button', name='开始研究', exact=True).click()
        dialog = page.locator('dialog[open]')
        assert not dialog.locator('#auth-model-calls').is_checked()
        dialog.locator('#auth-jobs').fill('0')
        dialog.locator('#auth-submissions').fill('0')
        dialog.get_by_role('button', name='确认并开始').click()
        page.wait_for_selector('.observation-aperture[data-activity=true]')
        page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
        page.wait_for_timeout(100)
        before = frames()
        page.wait_for_timeout(140)
        assert frames() == before
        record('offscreen active field stops rendering')
        page.evaluate('window.scrollTo(0,0)')
        page.wait_for_timeout(100)
        before = frames()
        page.wait_for_timeout(100)
        assert frames() > before
        page.get_by_role('button', name='动效 开', exact=True).click()
        page.wait_for_timeout(80)
        before = frames()
        page.wait_for_timeout(100)
        assert frames() == before
        record('all-motion toggle stops active rendering')
        page.get_by_role('button', name='动效 关', exact=True).click()
        page.emulate_media(reduced_motion='reduce')
        page.wait_for_timeout(80)
        before = frames()
        page.wait_for_timeout(100)
        assert frames() == before
        page.get_by_role('button', name='02 点阵').click()
        assert page.locator('.source-pixel-grid').count() == 0
        expect(page.locator('.observation-aperture')).to_have_attribute('data-mode', 'dots')
        record('reduced motion freezes active rendering and skips pixel transition')
        page.emulate_media(reduced_motion='no-preference')
        page.get_by_role('button', name='01 线束').click()
        page.wait_for_selector('.observation-aperture[data-activity=false]', timeout=10000)
        page.wait_for_timeout(200)
        assert not errors, errors[:3]
        report = {'kind': 'additional native Demo presentation checks', 'url': args.url,
                  'checks': checks, 'console_errors': errors}
        (args.output / 'presentation-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == '__main__':
    main()
