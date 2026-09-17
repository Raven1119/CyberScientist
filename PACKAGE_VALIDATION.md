# 工程包自身验证

日期：2026-09-17。**22 项检查通过；这些检查不等于生产应用或真实平台联调通过。**

## 验证范围

JSON Schema 自校验、配置/Decision 示例、错误输入拒绝、模板 YAML 与本地 Markdown 链接；Chromium 中的三页交互、指导队列、安全文本渲染、经验修订/恢复、运行快照隔离、秘密不进入保存对象、配置恢复逻辑，以及 390px 窄屏无整页横向溢出。

原型交互期间没有外部网络请求，没有未捕获 JavaScript 异常。已人工查看桌面与移动端渲染。原型截图见 `prototype/preview.png`。详细逐项结果见 `checks/results.json`。

## 测试方法与限制

本次环境的受管 Chromium 阻止 localhost 和 file:// 导航，因此通过 Playwright `set_content` 渲染生成的 HTML。涉及跨页面保存/恢复的检查使用明确的内存 Storage 测试替身；另测了浏览器存储不可用时的降级。**未在本环境验证用户直接双击 HTML 的导航或真实 localStorage 持久性。**

没有启动真实 Codex、Kimi 或 Prime，也没有登录玻尔、调用模型、创建远程 Job 或上传 Attempt；没有生产后端、React 生产构建或科学成绩验收。

## 复现

检查脚本为 `checks/validate_package.py`。需要 Python、PyYAML、jsonschema、Playwright 和可用 Chromium。环境具备这些依赖后，在工作区运行：

```bash
python checks/validate_package.py
```

脚本会优先使用 `CHROMIUM_PATH` 或系统 Chromium，否则使用 Playwright 安装的 Chromium；输出写入不入 Git 的 `.package-checks/`。脚本使用显式 Storage 测试替身，不发起任何模型或平台请求。此脚本仅验证开工包，不能替代施工后端的测试。
