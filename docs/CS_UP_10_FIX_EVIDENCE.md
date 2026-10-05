# CS-UP-10 修复证据（分工作包追加）

W0 已提交并推送。W1 的真实投递、镜像验证和最终源码回归通过。
现代 Job 使用 bohr 2.7.8；未知创建按名称对账，只有完整查询确认不存在才重交原冻结输入。
27 个最小 Job 均拿到 ID、完成并取回证明；其中 20 个极小输入、5 个约24 MiB输入。
私有镜像通过 v4 构建，并在 Job 和沙箱启动；旧 v2 的业务148888仍存在。
历史科学失败与运输失败分别记录；缺少日志的案例保持 unknown。
W2、W3、W4、W5 尚未完成，后续在本文件逐项追加验收。
本卡没有新科研 Run、比赛提交或整轮彩排；没有执行 CS-UP-11。
原始回执、资源身份、完整轨迹、SQLite及账号材料只保存在本机忽略目录。

## W0：决定与基线

实际起点为 `042c4b6`，当前工作是其后继。工作区原任务卡和经验保留，未 reset。W0 新增 D-48–D-55、仅给 D-30 加部分取代标注；还原这两处变化后，整个设计文档与原文件字节 SHA 一致。W0 实现提交为 `56ee5506f8e2a338f95fb7906d8acba9b2eaa113`，推送已确认。

## W1a：Job 提交可靠性

### 修复前与实际代码修复

旧1.1.0在带输入的创建请求中遇到超时；最多三页的查询不能完整观察账号列表。现代JSON回执另有两个ID域，旧解析只认 `JobId:`，会把已经成功的创建记为 unknown。09 ABC 使用非法 `result_path=/data`，09另一个失败评分命令仍含 `<base64plan>`。

- 配置了新版 bohr 时，Job 使用原生 `job submit -i ... --input_directory ... -y --no-interactive -o json`。账号密钥只在后端子进程内注入，HOME/XDG及host限定应用进程。正确区分平台 `jobId` 和下载/日志/停止用的 `bohrJobId`；旧CLI保持兼容。
- 每次预约先持久化唯一名称、清单、权限和原输入字节。现代未知创建立即释放并发位，并由独立5秒调度触发查询；实际分页读取有重试、110秒整体截止与100页保护。短页、重复ID、变化总数、错误或部分结果不能证明不存在。
- 找到唯一精确名称就接上。至少60秒后，完整无错查询证明不存在，才持久保存一个新的重交操作ID。冻结清单的数据库SHA绑定同一读取缓冲；复制按原哈希及权限核验。历史unknown不自动重放。
- 原Job被找回的事实优先于 pending retry；子预约事务内和实际调度前再次检查父状态/ID。查询与重交在同一个可追踪、取消安全的后台任务中；取消async waiter不会假装native线程已结束，关机在实际线程未结束时返回不可关机。未登记同步查询默认只读。
- 连续两次现代创建失败的事实经持久指导队列交给原执行器，建议同项计算改用已授权沙箱；不自动新建沙箱。成功创建结束连续失败计数。非法结果盘、未替换占位符在预约前明确拒绝。
- 状态与费用来源来自实际查询API路径，不能靠可选 `bohrId` 字段猜接口。现代下载ZIP按native ID域定位，保持原所有字节/hash/归属核验。

### 所有历史异常案例

审计固定于施工前一致性SQLite及08/09保留快照，总账81条：Finished55、Failed15、unknown8、明确本地not_started3。远端投递分母78：无IDunknown8/78=10.26%，Failed15/78=19.23%，完成55/78=70.51%。Failed包含科学验证、依赖及科研脚本错误，**不能把23/78称为运输故障率**。以下每一行保留对应原回执和日志哈希；案例身份以本地operation SHA前缀对应，不发布账号轨迹。

首回执耗时是预约至首个持久回执事件的观察值，含冻结/上传/CLI，不能冒称纯创建HTTP时长；老记录没有分阶段网络遥测。输入大小来自原冻结输入或账本；没有资料时写 unknown。旧接口为1.1.0 `/openapi/v1/job/create`，组创建错误单独标注。

|案例 / operation SHA前缀|状态|接口|输入字节|至首回执秒|原始错误摘录 / 分类|当时网络证据|
|---|---|---|---:|---:|---|---|
|H01 / `0e6f06259b`|Failed|v1 job/create|322300|11.099|`HTTP error 403 / numpy1.26.4 wheel`；依赖下载失败|依赖源403已观察|
|H02 / `1ec782c33d`|Failed|v1 job/create|23691|13.523|`probe.py: [Errno 2]; ReadTimeoutError`；依赖下载及旧输入布局|files.pythonhosted.org读超时已观察|
|H03 / `0ce98fedba`|Failed|v1 job/create|25138|13.683|`HTTP error 403 / mpmath1.3.0`；依赖下载失败|依赖源403已观察|
|H04 / `cba57903f9`|Failed|v1 job/create|69940|10.897|`RuntimeError: self/scale implementation gate failed`；科学实现门禁拒绝|未记录当时网络遥测|
|H05 / `6d1a28f3b2`|unknown|v1 job/create|939799026|188.417|`Bohrium 请求超时；先对账，不重试变更请求`；大输入创建未知|创建超时；丢包/吞吐未知|
|H06 / `30a5e9ca34`|unknown|v1 job/create|422879|7.303|`context deadline exceeded (Client.Timeout exceeded while awaiting headers)`；创建未知|等待请求头超时；丢包/吞吐未知|
|H07 / `4e543de9c7`|Failed|v1 job/create|34504|11.826|`AssertionError / cgroup_v1_cpu_period`；科研资源探针断言失败|未记录当时网络遥测|
|H08 / `1cfed19374`|Failed|v1 job/create|24535188|45.475|`TypeError: dict() got multiple values for keyword argument 'elapsed_s'`；科研脚本异常|依赖下载成功；创建阶段网络未知|
|H09 / `6d6a76f8ca`|unknown|v1 job/create|24480131|9.559|`request canceled (Client.Timeout exceeded while awaiting headers)`；创建未知|等待请求头超时；丢包/吞吐未知|
|H10 / `5668d3d069`|Failed|v1 job/create|632216085|430.136|`PermissionError: [Errno 13] Permission denied: '<frozen-input>/bin/zstd'`；旧冻结权限缺陷|未记录当时网络遥测|
|H11 / `39e9d0c230`|Failed|v1 job/create|630708729|415.026|`part_one_compile_passed: false; part_two_compile_passed: true`；科研编译未通过|未记录当时网络遥测|
|H12 / `08dc43730b`|Failed|v1 job/create|630707272|406.765|`KeyError: 'project/Problem.lean'`；科研包缺项|未记录当时网络遥测|
|H13 / `bb820a4bdb`|Failed|v1 job/create|27379|10.929|`/usr/bin/time: No such file or directory; Exit code 127`；科研环境缺依赖|未记录当时网络遥测|
|H14 / `7efcc28eb7`|unknown|v1 job/create|24481643|182.961|`Bohrium 请求超时；先对账，不重试变更请求`；创建未知|创建超时；丢包/吞吐未知|
|H15 / `df85f660aa`|Failed|v1 job/create|58630|15.271|`Program exception, exit code (1)`；日志未取回，根因未知|未记录当时网络遥测|
|H16 / `58a797d49b`|Failed|v1 job/create|61878|12.359|`Program exception, exit code (124)`；超时退出，完整日志未取回|未记录当时网络遥测|
|H17 / `85df3fc1bf`|unknown|v1 job_group/add|79580256|5.145|`job_group/add: request canceled (Client.Timeout exceeded while awaiting headers)`；创建Job组未知|等待请求头超时；丢包/吞吐未知|
|H18 / `e7bd7d4f66`|unknown|v1 job/create|48608842|183.395|`Bohrium 请求超时；先对账，不重试变更请求`；创建未知|创建超时；丢包/吞吐未知|
|H19 / `3682e16b98`|unknown|v1 job/create|24168866|180.122|`Bohrium 请求超时；先对账，不重试变更请求`；创建未知|创建超时；丢包/吞吐未知|
|H20 / `32f2a795f5`|Failed|v1 job/create|15603095|27.232|`FileNotFoundError: 'input/science_package.zip'`；08旧评分下载布局|未记录当时网络遥测|
|H21 / `35efd7ac33`|Failed|v1 job/create|1718242|13.382|`AssertionError: Verifier disagrees with visual prediction: review before accepting`；09科学候选被验证器拒绝|Pillow安装成功；创建阶段网络未知|
|H22 / `1f9ebec4a1`|Failed|v1 job/create|5827980|19.631|`syntax error near unexpected token '>'`；09未替换命令占位符|未记录当时网络遥测|
|H23 / `38beb12ec4`|unknown|v1 job/create|30666|14.185|`Only automatic downloading of results to /personal or /share is supported. Please modify and retry.`；09非法结果盘路径|本地CLI拒绝；远端是否有资源仍未知|
|H24 / `c766e732ff`|not_started|本地未投递|unknown|4.258|`cannot unmarshal string into Go struct field JobJson.project_id of type int`；本地项目ID类型错误|未发起远端创建|
|H25 / `1fa3431b03`|not_started|本地未投递|unknown|1264.817|`本地冻结清单序列化 TypeError；bohr job submit 尚未调用`；本地冻结序列化失败|未发起远端创建|
|H26 / `1451f526d5`|not_started|本地未投递|unknown|365.208|`本地冻结清单序列化 TypeError；bohr job submit 尚未调用`；本地冻结序列化失败|未发起远端创建|

H01–H03 的日志中有内嵌ZIP：先验证原ARTIFACT_RECEIPT声明SHA再读取，验证失败的嵌入内容不作为证据。H15/H16当前只读平台观察分别确认退出1/124，完整日志不能取回，保留未知根因。既有权限恢复及旧布局修复继续接受回归；科研脚本、科学验证器和已有资源均不在本次运行中改写。

### 新版真实统计与阶段计时

|探针|数量|实际结果|CLI全阶段耗时（最小 / 中位 / 最大秒）|
|---|---:|---|---|
|极小输入，CPU2核4GiB，2分钟上限|20|20/20得到ID、Finished、下载证明通过|4.690 / 4.822 / 5.182|
|24 MiB随机数据加验证脚本|5|5/5得到ID、Finished、证明中的大小与SHA匹配原输入|26.475 / 28.282 / 29.817|
|私有镜像Job|1|Finished，Python3.10.6及Linux证明取回|4.965|
|带阶段计时的额外24 MiB Job|1|Finished，输入哈希验证证明取回|31.804|

本次机制探针总计27/27=100%，卡片必需25/25=100%。全部真实请求首次拿到ID，没有制造真实超时或重复扣费；超时后的自动接上、完整缺席重交和分页超时恢复由fake测试证明。该短探针样本不能保证未来平台永不故障，也不能与长科研Job的科学成功率直接比较。

实际CLI调用按独立对象存储传输输入。计时转发器只观察请求长度、时长、HTTP/业务码与响应字段名，凭据仅在内存中转发：

|步骤|HTTP体字节|起始秒|耗时秒|确认事项|
|---|---:|---:|---:|---|
|v4 job_group/add|56|0.101|2.337|得到组身份|
|v4 job/create|78|2.439|2.332|小型存储占位；返回store路径/上传凭据，未调度计算|
|对象上传与CLI衔接区间|输入约24 MiB|4.771|24.029|独立对象存储传输区间，包含本机打包/衔接，非纯上传HTTP计时|
|v4 job/add|665|28.800|2.516|输入上传后以小请求实际调度，返回两个ID域|

这说明上传与实际计算调度分开；并非所有名为create的HTTP请求都在上传之后。各细小Job元数据约312字节，额外计时探针为665字节，输入字节未塞入计算调度请求。

## W1b：私有镜像

按官方v2参数（纯小写名称、整数projectId、device=container、desc、buildType=1、base64 Dockerfile），最小 `FROM` 已验证公共Python镜像、`RUN echo ok` 仍返回HTTP200加业务148888/rpc error，无ID。名称/字段修正没有解决旧路由；没有证据确定是退役、网关还是后台具体实现故障。

同一最小Dockerfile通过原生2.7.8 `image build` 的 `/openapi/v4/sandbox_work/image/build` 成功拿到镜像ID；私有镜像列表确认条目及构建状态2。Job实际启动通过；首次沙箱启动提示 IMAGE_PREPARATION_IN_PROGRESS（HTTP400）而不是构建失败，等待约5分钟后再试成功。第二次创建47.234秒，sandbox exec返回exit0、Python3.10.6及预定marker。该本卡新建沙箱已清理，未改动或删除任何本卡前资源。

产品默认在已配置现代CLI时使用v4构建并对账；旧v2保留历史兼容。不再把HTTP200等同构建成功。已跑通的v4路线满足本卡机制验收，故没有额外申请环境包存储。具体Lean/CUDA/量化环境内容等S4审计之后整理，本次没有声称已打包。

### 证据位置、验证与剩余风险

所有真实材料保存在 `.package-checks/cs-up-10/`：`authorized-calls.json`（调用前预约）、`historical-job-cases-final.json`、`job-completion-final.json`、`job-proof-results.json`、`real-stage-timings.json`、私有镜像列表/Job/沙箱回执。27份证明ZIP的清单SHA为 `fc65e7d0d25932b29754004139245e127936d14b241e26b3f0c5b5c5b4059ead`。源数据库备份 SHA `b0247feb5271029cce5f16cea85a404333186d0db1df89b353f285b857c61106`，迁移只加列。

实际原代码保留到忽略目录，用相同fixture对照：JSON ID旧unknown→新accepted、旧分页超时partial→新重试第4页接上、旧非法结果盘/占位符已投递→新预约前拒绝、旧镜像148888→新v4身份接受；5项对照测试通过。Fake不是实际平台成功回执，两者分开。

两轴只读审查确认父ID竞态、冻结清单/权限、分页完整性、取消线程、费用来源等边界；标准审查追加的同缓冲区SHA修正有独立回归。现有测试没有删除或跳过；旧未知身份和付费最终账单仍待平台核验。

当前本卡真实额度消耗：CPU27/40、GPU0/3、sandbox2/20（一次400也保守计入）、镜像构建2/6、环境包存储0/1；四角色零科研探针0/4、旧Run完整复盘0/4。比赛模板无限预算不能扩大这些施工额度。

W1最终源码完整回归 `.venv/bin/pytest -q`：1057 passed，586.78秒；最后边界回归60 passed／29.29秒，真实脱敏回执离线重放27 passed／22.95秒，原代码前后对照5 passed／3.11秒。前端50 passed及构建通过，compileall和diff检查通过。数据库副本两次初始化后71条原Job的状态、ID、回执完整保留，integrity_check=ok。此前失败/中间回归日志保留，没有删除或跳过既有测试。W2–W4目前尚未验收。
