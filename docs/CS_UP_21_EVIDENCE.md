# CS-UP-21 验收证据

## W1 凭据检查

- 已实现：原文、URL/二重URL、JSON转义及Base64编码的已存凭据硬拦截；形状只匹配至少20字符令牌及私钥块。普通英文 token、bearer、password 不触发。
- 已实现：形状命中持久化单项复核；`ops gates --target comp` / `ops gate resolve <id> --false-positive --reason ... --target comp` 人工放行，仅相同内容哈希和同项有效；已存凭据禁止放行。原生记录不改写。
- 已实际验证：`.venv/bin/pytest -q tests/test_native_log_privacy.py tests/test_credential_gate_cs21.py`：20 passed in 7.23s。涵盖 RH-02 普通词组、编码原文、硬拦截不可放行、形状复核与内容变化重新拦截。
- 已实际验证：对RH-02探索原生15,743,272字节扫描，SHA256 `5aebd2234dea75ed1ee2d9f452712e81c4188ec8a3f05750c8299df35fd0def9`；新分类器无命中，读取前后原字节相同。私有记录 `.package-checks/cs21/w1-native-classifier.json` 同时核对比赛实际存储凭据。
- 尚未验证：比赛发布后的端到端提交、复核后自动续接与前端复核（W5/W6）。
