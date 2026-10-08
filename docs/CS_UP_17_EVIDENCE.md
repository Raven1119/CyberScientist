# CS-UP-17 验证记录

原始回执、凭据和原生记录只保存在忽略的本地验证目录 `.package-checks/cs-night-1009/`。不将平台接受请求等同于科学验证。

| 项 | 实现与验收事实 |
|---|---|
| W0 | D-78及升级计划已记录。本地只读/打包；新题默认常驻Bohrium沙箱，长大计算使用Job。历史Run快照不覆盖。 |
| W1 | docs/JOB_FAILURES_1008.md含69行：36成功、12环境假设、3时限相关、4科学设置、3脚本错误、11根因unknown。缺少统一时间证据时浪费墙钟保持unknown；16个预检候选不等于已经消除16次失败。 |
| W2 | PI所选目录镜像按Run幂等创建常驻沙箱，能力索引可查询；先方法审批后创建。后台启动与轮询持久化，未知不重发；实际命令有独立超时，日志实时可读。30项回归通过cs17-w2-final-tests.log（40.79秒）。旧题私有账本真实沙箱12.908秒创建，后台三段63字节日志、退出0，随后原生删除及只读对账deleted，证据sandbox-first-native/background-result.json及reclaimed.json。最早原生协议探针另建一箱16.05秒并回收。 |

## W2 硬性缺口和授权核对

- **自动续期不通过**：已安装原生bohr 2.7.8的sandbox命令与官方沙箱文档未提供续期入口；不能猜API，也不能改本地expires_at冒充远端续期。替代为在现有授权内一次申请可用寿命（扣除创建余量），到期回收并使用同镜像Job；保留明确renewal=unavailable_in_native_cli事实。后续需供应商提供续期协议才可实现真正续期。
- 实际quota读取并发上限20、可用20，足够10题各一个；系统沙箱并发默认无额外上限，数量仍受各Run授权控制。建议每题至少1箱、按预计持续时长授权分钟数；10题连续24小时需合计14400沙箱分钟。现有模型会话配额10另需核对20个PI+执行者会话，不把沙箱额度视为模型额度。
- 真实回退Job 23509654使用同一ABACUS镜像，平台已Finished；该次触发原因是私有验证授权不足，并非TLS。失败注入后的真实Job另行核实，不混淆两次原因。全过程未创建新的科研Run。
- 原始失败、中断、未发送POST记录保留。验证授权账本保守计入一次已证明创建前拒绝和一次缺tag的镜像请求，不用被拒绝请求的差额增加预算。

## W3 强制Job预检

新sandbox_first_version=1在任何Job预留之前检查Python编译/Bash语法、入口及常量路径、镜像命令/依赖/路径事实、联网操作、backward_files、三倍冒烟时限和ABACUS关键INPUT/可动标志。镜像事实不全时只在已拥有、同镜像且授权有效的沙箱快速探测；没有可靠事实就拒绝Job。probe/allow_network_install不能绕过新策略。动态命令明确给出未核查警告，不声称静态分析能证明所有动态行为。历史Run保留旧快照政策。

15项首轮强制检查通过；加入Python内联/子进程及审查缺陷回归后33项通过（cs17-review-final-tests.log，48.22秒）；旧预检兼容29项通过cs17-w3-compat.log。初次审查回归3项失败原样保留，分别为测试写不存在的expired状态、重组shell遗漏产物重定向和fixture未授权Job；已修复后重新验证。

两轴审查修正：跨后端同ID重放、后台关机/授权检查、迟到启动回执回退终态、题目结束未轮询后台阻止回收、创建等待期间暂停仍投递、远端预检先于授权，以及heredoc/MPI/内联Python/cd/--no-index解析。新增回归逐一覆盖；未知后台操作在到期后仍查询原操作，不能改走Job重做。

W2失败注入确认：创建前TLS失败由明确fixture注入，实际原生Job23509669随后使用同ABACUS镜像，平台Finished（cs17-tls-fallback.log）；不将注入的TLS故障称为平台实际故障。科学产物下载另行核对。

最终预检审查补上解释器文件后缀绕过和大于2MB脚本静默省略：按解释器识别.txt脚本，支持-O/-e、嵌套Bash与env包装内联Python；未确认解释器的入口准确拒绝。大于2MB脚本及ABACUS关键输入在远端探测和Job预约前拒绝。52项定向回归通过（cs17-interpreter-final-2.log，27.17秒），规格轴7个纯解析复核均按预期阻断，标准轴无阻断。

两次实际回退Job的产物均已通过原生接口下载：23509654正文为same-image-job-fallback，SHA256为8482a4af8facba8ef59bbb02b1431621072013c44ddb9d5b5a441393c2b3b1b7；23509669正文为tls-failure-fallback，SHA256为0e273b1ca7b5fc957f1b5b12514f5e6a211865db436edaeff49b1354601a656a。私有证据sandbox-first/fallback-output-evidence.json。

## W4 模板与组合镜像

SCF与cell-relax完整案例在skills/cyberscientist-job-spec/attachments/abacus。模板预检INPUT和可动标志，最终检查最后一次SCF成功及其后的Finish Time；弛豫还要求最后结构优化成功。失败/截断/后来SCF失败均有回归。未修改技能正文、文献提示或原始科学日志。

官方ABACUS基础镜像registry.dp.tech/davinci/abacus-source-code:20260717010446；私有镜像172937实际构建状态2，985秒。/opt/science固定ase3.26.0、pymatgen2025.5.28、spglib2.6.0、phonopy2.39.0、pybader0.3.12、dpdata0.2.25，实际全部import成功，最小Si SCF及pybader默认pickle、电荷守恒检查退出0，后台观察14.88963秒。已登记competition-materials-20261009。原始SCF日志SHA256为4fb6fcb92d8dd8f136e504ea85497f58687100ac8fe1c91dcbc51c24d5060c1c。

限制：pybader dat输出使用pandas已删除接口，默认pickle实测成功；固定dpdata需要临时适配新ABACUS能量/应力标题，原文件不改。cell-relax模板有应用回归，尚未实际跑弛豫；卡要求的真实SCF和pybader已满足。首次失败及错误函数名/重复观察操作ID的拒绝日志保留。

## W5 工具链与离线文件

| 名称 | 实际验证 | 运行位置 |
|---|---|---|
| 官方DeePMD-kit 3.2.0 | dp版本、import、LAMMPS帮助及真实三原子DP势run 0退出0 | registry.dp.tech/dptech/deepmd-kit:3.2.0-sm89；dp/lmp；内置water/dpa2/frozen_model.pth |
| 离线组合镜像172951 | 实际构建状态2；从新沙箱读取权重和219赝势文件，并重新完成六包import、最小SCF、pybader；后台观察15.001575秒 | registry.dp.tech/dptech/dp/native/prod-88474/90229/competition-materials-assets:v1791488554；/opt/science/bin/python |
| DPA4-Neo-OMat24-v20260805 | 4583819字节；SHA256 fd7f34ae28f921201e4a0328ddf56179892752084f8363e7796038201471c989，新镜像沙箱校验通过 | 上述离线镜像 /opt/competition-assets/models/DPA4-Neo-OMat24-v20260805.pt |
| SG15 ONCV PBE | 官方2020-02-06归档5994386字节，SHA256 3f3bd74aa5d6e0b038218a6051bb99ed9469dc03d0f05b3ec8a523f0f7a7dff0；沙箱219文件可读 | 上述离线镜像 /opt/competition-assets/sg15 |
| dflow | pydflow1.8.133，实际import dflow退出0 | .cyberscientist/toolchain-venv/bin/python |
| Bohrium OpenAPI | 官方bohrium-sdk0.15.0，实际import bohrium退出0 | 同一专用客户端环境 |

上述6条均进入能力索引，每条名称/用途/位置来自实际验证后的行政登记；未验证或无有效回执哈希的条目不暴露。新离线目录为competition-materials-assets-20261009，官方GPU目录为official-deepmd-3-2-sm89-20261009，runtime_environments的材料起点切换为172951；原目录保留。

来源：[DPA4官方材料权重](https://huggingface.co/deepmodelingcommunity/DPA4-OMat24)、[DeePMD预训练命令](https://docs.deepmodeling.com/projects/deepmd/en/stable/cli.html)、[SG15官方发布](http://www.quantum-simulation.org/potentials/sg15_oncv/)、[dflow官方仓库](https://github.com/deepmodeling/dflow)、[Bohrium OpenAPI官方客户端](https://github.com/dptech-corp/bohrium-openapi-python-sdk)。最新可用限定为已核实公开发布的材料OMat预训练条目20260805；DPA4C-OMat仓库无可下载权重，不把空仓库当新版可用权重。HF主站下载失败后使用镜像取文件，SHA与官方元数据完全一致。Neo文件可读不等于特定推理后端兼容性已验证。

CPU沙箱运行官方GPU镜像时LAMMPS因libcuda.so.1无效失败，不能把管道退出0当通过；4090配置实测通过。个人存储备份上传后SG15元数据/挂载未核实，不用该备份作为离线可用性证据；最终采用镜像快照。构建请求累计保守计3次，其中一次缺tag在创建前拒绝，无第四次构建。

可审阅交付：组合镜像Dockerfile/描述、离线资产清单、客户端冻结锁文件、ABACUS两个附件案例；工具链速查仅占位目录skills/cyberscientist-toolchain-reference，正文等待设计助手，不冒称已启用。私有证据toolchain-registration.json、assets-snapshot-poll.json、deepmd-lammps-smoke.json、fullstack-clients-result.json；原生原文不入Git。

## W6 监控故障表草稿

docs/MONITOR_FAULT_TABLE_DRAFT.md覆盖卡要求的10类故障，每行均有默认动作、首次观察起算的明确时限和超时上报/继续方式。监控指导只经PI持久队列；unknown不重放、口头数值不覆盖日志、评分延迟不伪装完成。镜像准备后端45分钟上限与监控10分钟首上报分别列出，避免把草稿时限冒称远端超时。策略定稿由设计助手审阅交付。
