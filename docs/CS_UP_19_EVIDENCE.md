# CS-UP-19 验收证据

本卡由用户重新授权执行。真实提交0、镜像构建0；真实模型调用仅W2冒烟。未完成项持续列在STATUS，不以模拟测试替代真实闭环。

## W1 当前比赛快照

- 私有仓库：https://github.com/Raven1119/CyberScientist-comp，GitHub查询isPrivate=true。
- main快照提交：f5f9b571b44694fbc19d541fdf9dafd2bf82cecb；远端refs/heads/main与本地HEAD一致。
- 发布版本：1285f164b878cd5ba7839554762680314de59d43。264个发布文件逐项复核清单SHA，另导出版本、发布清单、脱敏设置、脱敏Codex配置、23个启用技能清单、两层目录名称/大小，共271文件。
- 完整导出清单：[export-manifest.json](https://github.com/Raven1119/CyberScientist-comp/blob/f5f9b571b44694fbc19d541fdf9dafd2bf82cecb/snapshot/export-manifest.json)。
- 现有已知秘密扫描与ASP、API token、Bearer凭据、AccessKey值、长base64/JWT、私钥块扫描：271文件、0命中。初次扫描将代码中的函数名判为AccessKey值；修正为凭据值模式后重扫，未修改清单文件字节。位置记录留在本机私有证据，不输出匹配值。
- 导出目录/home/wmywb/CyberScientist-comp-export，与比赛目录分离；比赛目录没有.git。未导出auth.json、秘密库、数据库、运行工作区、原生记录、虚拟环境、日志、备份或历史归档。两层目录树只包含名称、类型和大小。
- 命令：tools/export_comp_snapshot.py --root /home/wmywb/CyberScientist-comp --output /home/wmywb/CyberScientist-comp-export；GitHub建私库、推送main、repo view、ls-remote。
- 安全回归：tests/test_comp_snapshot_cs19.py，3 passed in 1.17s；覆盖原始字节、凭据排除/脱敏、违规清单、清单字节失配、扫描不回显。

## 未完成验收

W2–W8继续执行；W2第5步依赖W4/W5接线。
