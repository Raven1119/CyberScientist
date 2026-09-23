"""邮箱账号的平台适配器边界。

注册/提交/查分都经此层；真实平台（Bohrium Playground）凭据未配置时
返回准确缺项，绝不编造响应。Demo 适配器只产本地合成账号（is_demo=1），
分数永远 unknown——不假装评分能力。

真实适配器的端点形状来自官方文档 GET /api/docs/dev/AGENT_API.md
（2026-09 抓取快照在 checks/results/AGENT_API.md），关键通路：
- 注册实验账号 = 人类操作者调 POST /agent/register（文档 Option A，
  立即返回 agent 的 asp_ token，无需邮箱验证）
- 提交 = POST /challenges/{id}/attempts（multipart，status=draft）
  → zip 包再 POST /attempts/{id}/bundle → POST /attempts/{id}/submit
- 查分 = GET /api/attempts/{id}/score；只有 scoringState.scoreIsFinal
  为真才返回分数，否则如实 None
"""
from __future__ import annotations

import itertools
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Protocol


class PlatformError(Exception):
    """只有确认未产生远端副作用才允许释放预占。"""
    def __init__(self, message: str, *, no_side_effect: bool = False):
        super().__init__(message)
        self.no_side_effect = no_side_effect


def public_feedback(value: Any, *secrets: str | None) -> Any:
    """Retain platform evidence while removing credentials from response fields."""
    if isinstance(value, dict):
        return {str(key): public_feedback(item, *secrets)
                for key, item in value.items()
                if not re.search(r"token|password|secret|authorization|cookie|api.?key",
                                 str(key), re.IGNORECASE)}
    if isinstance(value, list):
        return [public_feedback(item, *secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[redacted]")
        return re.sub(r"\basp_[A-Za-z0-9_-]+|\bBearer\s+\S+", "[redacted]",
                      value, flags=re.IGNORECASE)
    return value


def final_score(body: Any) -> float | None:
    """Only an explicit finality claim and a finite numeric score are usable."""
    if not isinstance(body, dict):
        return None
    state = body.get("scoringState")
    if not isinstance(state, dict) or state.get("scoreIsFinal") is not True:
        return None
    score = state.get("displayScore")
    if score is None:
        score = body.get("score")
    if isinstance(score, bool):
        return None
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


class MailboxPlatform(Protocol):
    name: str
    is_demo: bool

    def register_account(self) -> dict[str, str]:
        """注册一个实验账号，返回 {"email": ..., "password": ...}。"""
        ...

    def submit_package(self, email: str, secret: str | None,
                       package_path: str, challenge_id: str,
                       meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """提交现成提交包，返回 {"accepted": bool, "receipt": ...}。"""
        ...

    def fetch_score(self, email: str, secret: str | None,
                    submission_ref: str) -> float | None:
        """拉回官方得分；不知道返回 None（不编造）。"""
        ...


class DemoMailboxPlatform:
    """本地演示平台：零外部调用，全部产物标记 is_demo。"""

    name = "demo"
    is_demo = True
    _counter = itertools.count(1)

    def register_account(self) -> dict[str, str]:
        n = next(self._counter)
        return {"email": f"demo-{n}@demo.local", "password": f"demo-{n}"}

    def submit_package(self, email: str, secret: str | None,
                       package_path: str, challenge_id: str = "",
                       meta: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"accepted": True, "receipt": f"demo-receipt:{email}"}

    def fetch_score(self, email: str, secret: str | None,
                    submission_ref: str) -> float | None:
        return None  # Demo 无评分能力：如实 unknown


def _encode_multipart(fields: dict[str, str],
                      files: list[tuple[str, str, bytes]],
                      ) -> tuple[bytes, str]:
    """最小 multipart/form-data 编码。files: (字段名, 文件名, 内容)。"""
    boundary = f"----cyberscientist{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
            f"\r\n\r\n{value}\r\n".encode("utf-8"))
    for field, filename, content in files:
        safe_name = filename.replace('"', "_").replace("\r", "_") \
            .replace("\n", "_")
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{field}";'
            f' filename="{safe_name}"\r\nContent-Type: application/octet-stream'
            f"\r\n\r\n".encode("utf-8") + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class BohriumPlaygroundPlatform:
    """Bohrium Playground 真实适配器（端点形状见模块 docstring 来源）。

    operator_token 是人类操作者的 asp_ token，用于注册实验 agent 账号；
    提交/查分用各邮箱自己的 token（secret 参数）。
    """

    name = "bohrium_playground"
    is_demo = False

    def __init__(self, base_url: str, operator_token: str | None = None,
                 timeout: int = 60, framework: str = "CyberScientist"):
        self.base_url = base_url.rstrip("/")
        self.operator_token = operator_token
        self.timeout = timeout
        self.framework = framework

    # ---------- HTTP ----------

    def _http(self, method: str, path: str, token: str | None = None,
              json_body: Any = None,
              form: tuple[dict[str, str], list[tuple[str, str, bytes]]]
              | None = None) -> Any:
        headers: dict[str, str] = {}
        data: bytes | None = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data, headers["Content-Type"] = _encode_multipart(*form)
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise PlatformError(
                f"平台接口 {method} {path} 返回 HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise PlatformError(
                f"平台接口 {method} {path} 网络失败: {exc.reason}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}

    # ---------- 协议 ----------

    def register_account(self) -> dict[str, str]:
        """文档 Option A：人类 token 注册 agent 账号，立即拿到 asp_ token。"""
        if not self.operator_token:
            raise PlatformError(
                "未配置 playground.token_secret_ref（操作者 token），"
                "无法注册实验账号")
        name = f"cyberscientist-exp-{uuid.uuid4().hex[:6]}"
        resp = self._http("POST", "/agent/register",
                          token=self.operator_token,
                          json_body={"name": name, "framework": self.framework})
        token = resp.get("token") if isinstance(resp, dict) else None
        agent = resp.get("agentUser") if isinstance(resp, dict) else None
        if not token or not isinstance(agent, dict):
            # 不 dump 响应体：其中可能含有新签发的 token
            raise PlatformError(
                "注册响应缺少预期字段（token/agentUser），注册未完成")
        return {"email": agent.get("name") or name, "password": token,
                "platform_account_id": str(agent.get("id") or "")}

    def submit_package(self, email: str, secret: str | None,
                       package_path: str, challenge_id: str = "",
                       meta: dict[str, Any] | None = None) -> dict[str, Any]:
        """草稿 attempt → （zip 包）上传 bundle → submit。真实提交动作。"""
        if not secret:
            raise PlatformError(f"邮箱 {email} 无平台凭据，不能提交", no_side_effect=True)
        if not challenge_id or challenge_id.startswith("demo://"):
            raise PlatformError(
                "该题目未关联真实平台 challenge"
                f"（platform_challenge_id={challenge_id or '空'}），"
                "无法定位提交目标", no_side_effect=True)
        meta = meta or {}
        pkg = Path(package_path)
        if not pkg.is_file():
            raise PlatformError(f"提交包文件不存在: {package_path}", no_side_effect=True)
        package_bytes = meta.get("package_bytes")
        if package_bytes is None:
            package_bytes = pkg.read_bytes()
        q_cid = urllib.parse.quote(challenge_id, safe="")

        trace = meta.get("trace") or [{
            "type": "tool_call",
            "title": "Submit reproduction package",
            "body": f"CyberScientist 提交现成包 {pkg.name}"
                    f"（{len(package_bytes)} 字节）",
        }]
        fields = {
            "method": meta.get("method") or "CyberScientist reproduction",
            "type": "agent",
            "status": "draft",
            "outcome": meta.get("outcome") or "partial",
            "harness": meta.get("harness") or "CyberScientist",
            "trace": json.dumps(trace, ensure_ascii=False),
        }
        if meta.get("model"):
            fields["model"] = meta["model"]
        # 自报指标：JSON 提交包的内容直接作为 results_json 表单字段
        # （programmatic_grader 从 attempt.resultsJson 读数）
        results = meta.get("results_json")
        if results is None and pkg.suffix.lower() == ".json":
            try:
                results = json.loads(package_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
                raise PlatformError(
                    f"JSON 提交包无法解析: {pkg.name}", no_side_effect=True) from exc
        if results is not None:
            fields["results_json"] = json.dumps(results, ensure_ascii=False)
        on_stage = meta.get("on_stage") or (lambda *args: None)
        on_feedback = meta.get("on_feedback") or (lambda *args: None)
        on_stage("create_sent")
        attempt = self._http(
            "POST", f"/challenges/{q_cid}/attempts",
            token=secret, form=(fields, []))
        attempt_id = attempt.get("id") if isinstance(attempt, dict) else None
        if attempt_id is None:
            raise PlatformError("创建 attempt 响应缺少 id 字段，提交未完成")
        on_stage("draft_created", str(attempt_id))
        on_feedback("create", public_feedback(attempt, secret, self.operator_token))
        q_aid = urllib.parse.quote(str(attempt_id), safe="")

        bundle_uploaded = False
        if pkg.suffix.lower() == ".zip":
            on_stage("upload_sent", str(attempt_id))
            uploaded = self._http("POST", f"/attempts/{q_aid}/bundle", token=secret,
                                  form=({}, [("bundle", pkg.name, package_bytes)]))
            on_feedback("bundle", public_feedback(uploaded, secret, self.operator_token))
            bundle_uploaded = True
            on_stage("bundle_uploaded", str(attempt_id))

        on_stage("submit_sent", str(attempt_id))
        submitted = self._http("POST", f"/attempts/{q_aid}/submit", token=secret)
        on_feedback("submit", public_feedback(submitted, secret, self.operator_token))
        on_stage("submitted", str(attempt_id))
        return {"accepted": True, "receipt": str(attempt_id),
                "bundle_uploaded": bundle_uploaded}

    def fetch_score(self, email: str, secret: str | None,
                    submission_ref: str) -> float | None:
        """GET /attempts/{id}/score；scoringState.scoreIsFinal 才采信。"""
        return final_score(self.fetch_score_details(email, secret, submission_ref))

    def fetch_score_details(self, email: str, secret: str | None,
                            submission_ref: str) -> dict[str, Any] | None:
        """Preserve pending, failed, final and eligibility evidence for the UI."""
        if not submission_ref or submission_ref.startswith("demo-receipt:"):
            return None
        body = self._http(
            "GET",
            f"/attempts/{urllib.parse.quote(str(submission_ref), safe='')}"
            "/score",
            token=secret)
        return public_feedback(body, secret, self.operator_token) \
            if isinstance(body, dict) else None


def get_platform(name: str) -> MailboxPlatform:
    if name == "demo":
        return DemoMailboxPlatform()
    if name == "bohrium_playground":
        from . import config
        settings = config.load_settings()
        pg = settings.get("playground") or {}
        runtime = (settings.get("executor") or {}).get("runtime")
        framework = {"codex": "Codex", "kimi": "Kimi Code",
                     "prime": "Prime Agent"}.get(runtime)
        return BohriumPlaygroundPlatform(
            base_url=pg.get("base_url") or "https://play.bohrium.com/api",
            operator_token=config.resolve_secret(
                pg.get("token_secret_ref") or ""),
            framework=f"CyberScientist ({framework})" if framework else "CyberScientist")
    raise PlatformError(f"未知邮箱平台: {name}（可选: demo, bohrium_playground）")


def parse_challenge_slug(raw: str) -> str | None:
    """从平台题目 URL 或裸 slug 解析 challenge id；无法解析返回 None。"""
    raw = raw.strip()
    if not raw:
        return None
    match = re.search(r"/challenges?/([^/?#]+)", raw)
    if match:
        slug = match.group(1)
    elif "/" not in raw and " " not in raw:
        slug = raw
    else:
        return None
    if re.fullmatch(r"[A-Za-z0-9._~-]+", slug):
        return slug
    return None


def fetch_platform_challenge(base_url: str, slug: str,
                             token: str | None = None) -> dict[str, Any]:
    """只读拉取平台题目详情（GET /challenges/{id}，公开端点无需 token）。

    返回含 title/title_zh/content 等字段的 JSON；平台 404/网络失败抛
    PlatformError，由调用方转成准确缺项。
    """
    platform = BohriumPlaygroundPlatform(base_url)
    quoted = urllib.parse.quote(slug, safe="")
    data = platform._http("GET", f"/challenges/{quoted}", token=token)
    if not isinstance(data, dict) or "_raw" in data:
        raise PlatformError(f"平台题目 {slug} 详情不是 JSON，契约未核实")
    return data
