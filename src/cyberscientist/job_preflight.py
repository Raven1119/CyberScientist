"""Side-effect-free source and image fact checks before a Bohrium reservation."""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any


class PreflightError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


_PYTHON = re.compile(r"(?:^|\s)(?:python(?:[0-9.]+)?|/usr/bin/python(?:[0-9.]+)?)\s+([^\s;&|]+)")
_INSTALL = re.compile(r"\b(?:pip\s+install|uv\s+pip|conda\s+install|mamba\s+install)\b")


def _entry(command: str, declared: str | None) -> str | None:
    if declared:
        return declared
    match = _PYTHON.search(command)
    if not match:
        return None
    entry = match[1].strip("'\"")
    cd = re.search(r"(?:^|[;&|]\s*)cd\s+([^\s;&|]+)\s*(?:&&|;)", command)
    return (str(Path(cd[1].strip("'\"")) / entry) if cd and not Path(entry).is_absolute()
            else entry)


def _module_path(base: str, module: str, files: dict[str, bytes],
                 literal: bool = False) -> str | None:
    stem = (base + (module if literal else module.replace(".", "/"))).lstrip("/")
    for candidate in (stem + ".py", stem + "/__init__.py"):
        if candidate in files:
            return candidate
    return None


def _requirements(files: dict[str, bytes]) -> set[str]:
    packages = set()
    for name, data in files.items():
        if Path(name).name.startswith("requirements") and Path(name).suffix == ".txt":
            for line in data.decode("utf-8", "replace").splitlines():
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
                if match:
                    packages.add(match[1].lower().replace("-", "_"))
    return packages


def check_sources(files: dict[str, bytes], command: str = "", entry: str | None = None,
                  allow_network_install: bool = False) -> dict[str, Any]:
    root = _entry(command, entry)
    if root and root not in files:
        raise PreflightError("MISSING_ENTRY", f"入口文件未打包：{root}")
    if _INSTALL.search(command):
        if not allow_network_install:
            raise PreflightError("NETWORK_INSTALL_UNDECLARED", "计算命令包含未声明的联网安装")
        pinned = any(Path(name).name.startswith("requirements") and
                     all(not line.strip() or line.lstrip().startswith("#") or
                         re.search(r"(?:==|@|===)\s*[^\s]+", line)
                         for line in data.decode("utf-8", "replace").splitlines())
                     for name, data in files.items() if name.endswith(".txt"))
        if not pinned:
            raise PreflightError("UNPINNED_INSTALL", "联网安装需要带版本锁定的 requirements 文件")
    if not root:
        return {"entry": None, "third_party": [], "dynamic_import_unchecked": False,
                "api_checked": False}
    requirements = _requirements(files)
    queue = [root]
    seen = set()
    third_party = set()
    missing = set()
    dynamic = False
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            tree = ast.parse(files[name].decode("utf-8", "replace"), filename=name)
        except SyntaxError as exc:
            raise PreflightError("INVALID_PYTHON", f"Python 语法无法解析：{name}") from exc
        parent = Path(name).parent.as_posix()
        base = "" if parent == "." else parent + "/"
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
                label = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
                if label in ("__import__", "import_module"):
                    dynamic = True
            imports: list[tuple[str, bool]] = []
            if isinstance(node, ast.Import):
                imports = [(alias.name, False) for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    prefix = base
                    for _ in range(node.level - 1):
                        prefix = str(Path(prefix).parent).rstrip("/") + "/"
                    if node.module:
                        imports = [(prefix + node.module.replace(".", "/"), True)]
                    else:
                        imports = [(prefix + alias.name, True)
                                   for alias in node.names if alias.name != "*"]
                elif node.module:
                    imports = [(node.module, False)]
            for module, relative in imports:
                module = module.strip("/")
                root_dir = str(Path(root).parent)
                candidate = (_module_path("", module, files, literal=relative) or
                             (_module_path(root_dir + "/", module, files)
                              if not relative and root_dir != "." else None))
                if candidate:
                    queue.append(candidate)
                    continue
                top = module.split("/", 1)[0].split(".", 1)[0]
                if relative:
                    missing.add(module.replace("/", ".") + ".py")
                elif top in sys.stdlib_module_names:
                    continue
                elif top.lower().replace("-", "_") in requirements:
                    third_party.add(top)
                elif importlib.util.find_spec(top) is not None:
                    third_party.add(top)
                else:
                    missing.add(module.replace(".", "/") + ".py")
    if missing:
        raise PreflightError("MISSING_LOCAL_MODULE", "本地模块未打包", {"missing": sorted(missing)})
    return {"entry": root, "third_party": sorted(third_party),
            "dynamic_import_unchecked": dynamic, "api_checked": False}


def check_image_facts(report: dict[str, Any], image: str, api_checks: list[dict[str, Any]],
                      facts: dict[str, Any] | None) -> dict[str, Any]:
    required = set(report["third_party"])
    required.update(str(check.get("module", "")).split(".")[0] for check in api_checks)
    packages = facts.get("packages", {}) if isinstance(facts, dict) else {}
    missing = sorted(pkg for pkg in required if pkg and pkg not in packages)
    if missing or (api_checks and not facts):
        code = "import importlib, inspect, json\n"
        code += "checks=" + repr(api_checks) + "\n"
        code += "packages=" + repr(sorted(required)) + "\n"
        code += "out={'packages': {}}\n"
        code += "for root in packages:\n"
        code += " m=importlib.import_module(root)\n"
        code += " out['packages'][root]={'version':getattr(m,'__version__',None),'api':{}}\n"
        code += "for check in checks:\n"
        code += " m=importlib.import_module(check['module']); obj=getattr(m,check['attr']); root=check['module'].split('.')[0]\n"
        code += " out['packages'][root]['api'][check['module']+'.'+check['attr']]={'params':list(inspect.signature(obj).parameters)}\n"
        code += "import os; os.makedirs('results',exist_ok=True)\n"
        code += "open('results/facts.json','w').write(json.dumps(out,sort_keys=True))\n"
        raise PreflightError("IMAGE_FACTS_MISSING", "镜像依赖/API 事实未覆盖",
            {"missing": missing, "probe": {"file": "cs_probe.py", "source": code,
             "job": {"command": "python cs_probe.py", "image_address": image,
                     "machine_type": "c2_m2_cpu", "max_run_time": 5}}})
    for check in api_checks:
        package = packages.get(check["module"].split(".")[0], {})
        sig = package.get("api", {}).get(check["module"] + "." + check["attr"])
        if not sig:
            raise PreflightError("IMAGE_FACTS_MISSING", "镜像缺少指定 API 签名事实",
                {"api": check})
        absent = sorted(set(check.get("params") or []) - set(sig.get("params") or []))
        if absent:
            raise PreflightError("API_MISMATCH", "镜像 API 参数不匹配",
                                 {"api": check, "missing_params": absent})
    return report | {"api_checked": bool(api_checks), "image_facts_present": facts is not None}
