# CS-UP-15 验收证据

本卡实现了官方CLI构建提交、科学/轨迹分开记录与早推、账号轮换和参考轨迹提示。真实新应用API提交已确认创建和Worker上传；严格同SHA、双实验账号、paired-block原生绑定、平台下载和旧unknown结案仍有缺口，不能整体标为验收通过。

## 实现与验证

| 项 | 结果 | 证据（私有目录 `.package-checks/cs-night-1009/`） |
|---|---|---|
| W0决定 | 已记录D-74/76/77/81及本轮有界授权 | docs/UPGRADE_DESIGN.md、DECISIONS.md；authorization.json |
| W1官方CLI路径 | 新API真实LiSi创建上传成功；CLI固定0.1.40，显式model/harness，六输出白名单与原生记录完整 | lisi-new-path-preflight.json、lisi-api-result.json、new-submission-hashes.json；数据库sub_8e446f6e58 |
| W1严格预演SHA=实投SHA | 不通过：官方每次构建写入时间，无固定时间参数；未修改官方CLI | 预演31915904…17a；实投ab837a06…8ec；替代核对科学输出逐字节、原生记录与实际Worker包SHA |
| W1每日首次平台包下载 | 无法判定：bundlePath=null，无同源下载URL；不猜私有路由 | daily-remote-audit-50211.json；本地官方包与Worker成员数/hash可核对 |
| W1 paired-block | 不通过：原满分包有原生记录，但缺本系统Trial绑定；不补造证明 | CS-UP-14 transport-paired-block-20261008/selection.json |
| W1旧unknown | 未结案：完整分页出现50139且哈希不能关联，ambiguous，不释放预约/重发 | legacy-lisi-unknown-reconciliation.json；原sub_ccc1b19416保留 |
| W2两新Agent | 已真实创建，均待本人认领；本地无可恢复登录凭据 | owned-agents-after.json、账号列表 |
| W2真实两账号 | 不通过：只有原实验账号可用；两新账号缺令牌，第五账号未配置 | authorization.json：注册2/2；不再注册、不Regenerate |
| W3真实回执回放 | 50127/50139字段正确入库，science事件先于receipt；新50211 science→receipt顺序已入库 | real-receipts-replayed.json、new-real-receipt-replay-50211.json；私有数据库回执事件 |
| W4参考提示 | 同一50139官方输入提示N11/N14，与平台相同；不打分/不阻断 | 50139-local-hint-calibration.json；w4-related.log：24 passed |
| W5应用回归 | 最终1649测试全部通过，2条依赖弃用警告；1065.24秒 | cs15-final-frozen-suite.log |
| W5前端 | 23文件106测试通过，生产构建通过 | cs15-front-final-2.log、cs15-build-final-2.log |

## 实际回执记录

只列结构化验收字段；真实原文和原始会话留私有数据库/忽略目录，不入Git。UNKNOWN不补零。

| Attempt | 本轮动作/账号 | 科学reward / score | 轨迹score / factor | 判定 / 扣分码 | 来源 / final / 计季 |
|---|---|---|---|---|---|
| 50127 | 历史真实abc回执只读回放；exp-89b8dd | 0 / 0 | 30.325 / 0.30325 | review；N08(-18)、N09(-30)、N11(-6)、N12(-32) | harbor_worker / true / false |
| 50139 | 历史真实LiSi回执只读回放；exp-89b8dd | 1 / 100 | 82.925 / 1 | accept；N11(-6)、N14(-8) | harbor_worker / true / false |
| 50211 | 本轮新应用API，sub_8e446f6e58；exp-89b8dd | 1 / 100 | 82.425 / 1 | accept；N11(-6)、N14(-8) | harbor_worker / true / false |

50211发送源封存SHA=6e1a39f9de5ce6b9639675774ffd460116d75263bbace66c025ae969586bee97；实际官方包SHA=ab837a062a1adcc8ec52f14ecf4fc5db8b5c42f8ab41e10d6a3e1c991a98d8ec。新API调用没有新建科研Run、Job或重算科学输出。验证授权累计提交1/6，账号注册2/2。

## 有界审查

基线e8de094；按code-review技能两轴并行只读审查，完整摘要在cs15-review.json。审查不代理实现。

### Standards

发现结束时间解析、重放账号选择、重发幂等、known-Attempt与并发释放约束问题；已修复。下载初始URL和跳转均限定相同scheme/netloc，避免跨源转发认证。

### Spec

发现unknown从预约时间计时、旧题解析、重放账号、更新提示无入口、ops跨账号同哈希和Run/Trial归属问题；已修复；另核对控制器的原生绑定事件。

Standards 4类问题、Spec 6项问题；两轴最严重的问题均是原验证入口拒绝/unknown可能误释放，已修复并补回归。最初失败和中间测试日志保留，不能代替最后全量。

## 遗留与替代方案

新账号cyberscientist-exp-f8ed7a、cyberscientist-exp-e8073a已经远端创建。首版在创建后漏导入config，临时JWT/随机密码未保存；这是实现错误，不是平台失败。现代码在POST之前保存密码，得到JWT立即保存，再换ASP令牌，并保留失败恢复材料。用户/平台方需为这两个既有账号恢复登录或另发API令牌；本轮不调用Regenerate。需再配置一个本人既有Agent，才能达到4实验+1收割。收割保持关闭。

官方构建时间导致预演和实投整包SHA不同，替代为输出和原生字节不变、实际官方包与Worker回执一致。平台下载URL缺失时保留unknown。paired-block缺可信绑定时保留原件，不把外部会话伪装成本地Trial。旧unknown有新增歧义时保留预约，避免重复提交。
