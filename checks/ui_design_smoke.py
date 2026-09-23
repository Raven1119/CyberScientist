"""Browser acceptance against checks/serve_ui_demo.py and the actual frontend.

Run with a Python environment containing Playwright and its Chromium browser:
    python checks/ui_design_smoke.py --url http://127.0.0.1:5173

No HTTP response mocking or synthetic running-state injection is used. The
native Demo brain/executor are scripted product adapters, not real models.
The server's isolation header is required before any UI mutation occurs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--output", type=Path, default=ROOT / "checks" / "shots" / "design-language")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    checks: list[dict] = []
    console_errors: list[str] = []
    api_failures: list[str] = []

    def record(name: str, **details) -> None:
        checks.append({"check": name, "passed": True, **details})

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1440, "height": 1100},
                                      device_scale_factor=1, locale="zh-CN")
        page = context.new_page()
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("response", lambda response: api_failures.append(f"{response.status} {response.url}")
                if "/api/v1/" in response.url and response.status >= 400 else None)
        health = context.request.get(args.url + "/api/v1/health")
        assert health.headers.get("x-cyberscientist-ui-demo") == "isolated-native-demo", "Refusing to mutate an unmarked workspace"
        assert health.json()["mode"] == "demo", "Demo mode required"
        record("isolated native Demo backend", health=health.json())

        def shot(name: str) -> None:
            page.screenshot(path=str(args.output / f"{name}.png"), full_page=True)

        def no_overflow(name: str) -> None:
            dimensions = page.evaluate("({viewport: innerWidth, scroll: document.documentElement.scrollWidth})")
            assert dimensions["scroll"] <= dimensions["viewport"] + 1, (name, dimensions)
            record(name + " fits viewport", **dimensions)

        def nav(label: str) -> None:
            page.get_by_role("navigation", name="主导航").get_by_role("button", name=label).click()
            expect(page.get_by_role("heading", name=label, exact=True)).to_be_visible()

        def start_demo() -> None:
            page.get_by_role("button", name="开始研究", exact=True).click()
            dialog = page.locator("dialog[open]")
            expect(dialog).to_be_visible()
            assert not dialog.locator("#auth-model-calls").is_checked()
            dialog.locator("#auth-jobs").fill("0")
            dialog.locator("#auth-submissions").fill("0")
            dialog.get_by_role("button", name="确认并开始", exact=True).click()
            expect(dialog).not_to_be_visible()
            page.wait_for_selector('.observation-aperture[data-activity="true"]', timeout=5000)

        def frames() -> int:
            return int(page.locator(".observation-field canvas").get_attribute("data-frames") or "0")

        page.goto(args.url)
        expect(page.get_by_text("演示模式", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="研究工作台", exact=True)).to_be_visible()
        page.wait_for_timeout(800)
        if page.get_by_text("还没有题目", exact=True).is_visible():
            shot("01-paper-empty")
            record("empty research state visible")
        else:
            checks.append({"check": "empty research state", "passed": None, "reason": "Backend already has Demo data; use a fresh helper process for this check"})

        page.get_by_role("button", name="导入题目", exact=True).first.click()
        dialog = page.locator("dialog[open]")
        expect(dialog).to_be_visible()
        shot("02-import-dialog")
        dialog.get_by_role("button", name="手动导入（标题+题面）", exact=True).click()
        dialog.locator("#import-title").fill("界面验收长标题：保留研究问题与证据来源，检查窄屏换行与输入可读性。" * 8)
        dialog.locator("#import-content").fill("这是一段仅用于界面输入验收的长文本，不代表科学结果。\n" * 30)
        shot("03-long-form")
        record("long input remains editable", characters=len(dialog.locator("#import-content").input_value()))
        dialog.get_by_role("button", name="导入演示题目", exact=True).click()
        dialog.get_by_role("button", name="导入", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(page.locator(".challenge-title")).to_be_visible()
        page.wait_for_timeout(800)
        no_overflow("1440px research")
        shot("04-paper-research")
        stable = frames()
        page.wait_for_timeout(180)
        assert frames() == stable, "An idle field must not animate"
        record("idle observation stays static")

        page.get_by_role("button", name="02 点阵", exact=True).click()
        page.wait_for_selector('.observation-aperture[data-mode="dots"]')
        page.wait_for_timeout(400)
        page.get_by_role("button", name="01 线束", exact=True).click()
        page.wait_for_selector('.observation-aperture[data-mode="threads"]')
        page.wait_for_timeout(400)
        assert page.locator(".observation-field canvas").count() == 1
        record("pixel mode switch leaves one live canvas")

        start_demo()
        shot("05-native-demo-running")
        first = frames()
        frame_a = page.locator('.observation-aperture').screenshot(path=str(args.output / '05-motion-a.png'))
        page.wait_for_timeout(160)
        second = frames()
        frame_b = page.locator('.observation-aperture').screenshot(path=str(args.output / '05-motion-b.png'))
        assert second > first, ("Native Demo activity did not advance frames", first, second)
        assert frame_a != frame_b, "Moving frames should produce visibly different images"
        record("native Demo busy state advances observation", before=first, after=second, images_differ=True)
        textarea = page.locator("#steer-text")
        if textarea.count() == 0:
            textarea = page.locator("textarea").first
        textarea.focus()
        page.wait_for_timeout(80)
        first = frames()
        page.wait_for_timeout(160)
        assert frames() == first, "Typing focus should pause ambient frames"
        record("writing pauses observation")
        textarea.evaluate("element => element.blur()")
        page.wait_for_timeout(80)
        first = frames()
        page.wait_for_timeout(160)
        assert frames() > first, "Ambient frames did not resume after writing"
        record("observation resumes after writing")
        page.get_by_role("button", name="暂停画面", exact=True).click()
        page.wait_for_timeout(80)
        first = frames()
        page.wait_for_timeout(160)
        assert frames() == first, "Explicit ambient pause should stop frames"
        record("explicit observation pause")
        page.get_by_role("button", name="恢复画面", exact=True).click()
        page.wait_for_selector('.observation-aperture[data-activity="false"]', timeout=10000)
        page.wait_for_timeout(180)
        first = frames()
        page.wait_for_timeout(180)
        assert frames() == first, "Completed Run should stay static"
        record("completed native Demo is a stable archive")
        shot("06-completed-demo")

        page.get_by_role("button", name="切换夜间主题").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "night")
        shot("07-night-research")
        page.get_by_role("button", name="专注", exact=True).click()
        shot("08-focus")
        page.keyboard.press("Escape")
        expect(page.get_by_role("navigation", name="主导航")).to_be_visible()
        record("focus view exits by Escape")

        for label, filename in (("经验库", "experience"), ("邮箱与提交", "mailbox"), ("连接与设置", "settings")):
            nav(label)
            page.wait_for_timeout(500)
            no_overflow("1440px " + label)
            shot("09-night-" + filename)
        nav("研究工作台")
        page.get_by_role("button", name="切换日间主题").click()
        page.set_viewport_size({"width": 390, "height": 844})
        for label, filename in (("研究工作台", "research"), ("经验库", "experience"), ("邮箱与提交", "mailbox"), ("连接与设置", "settings")):
            nav(label)
            page.wait_for_timeout(500)
            no_overflow("390px " + label)
            shot("10-mobile-" + filename)

        page.emulate_media(reduced_motion="reduce")
        nav("研究工作台")
        expect(page.get_by_role("button", name="静态", exact=True)).to_be_disabled()
        record("prefers-reduced-motion disables motion control")
        assert not console_errors, console_errors[:3]
        assert not api_failures, api_failures
        record("no browser console or API response errors")
        report = {"kind": "native Demo UI acceptance; no real model/science integration", "url": args.url,
                  "checks": checks, "console_errors": console_errors, "api_failures": api_failures}
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
