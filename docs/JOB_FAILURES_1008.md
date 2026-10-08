# 10-08 LiSi：69 个 Job 只读失败归因

来源：开工一致性账本before.sqlite（私有路径.package-checks/cs-night-1009/），run_8a21b7d249；69个，Failed33、Finished36。没有重跑计算、修改旧Job或删除资源。原始回执/原生会话不在本文，逐项结构化来源与日志哈希保存在job-failures-1008.json。

退出码从平台errorInfo或归档RESULT rc/exit提取，绝不用创建CLI的exit0充当科学任务exit0。spendTime为平台报告、现有适配器按秒映射的值；它不能独立证明从启动到终止的墙钟，更不能相加当作7.5小时串行用时。失败的独立墙钟损失缺少统一起止时间，保留unknown；替代提供平台报告时长。成功行不归入失败。

| Job ID / bohr ID | 状态 | 任务退出码 | 第一错误/直接失败事实 | 归类 | 平台spendTime(s) | 浪费墙钟(s) | 依据/不确定性 |
|---|---|---|---|---|---:|---|---|
| 23502045 / 20855311 | Failed | 1 | Program exception, exit code  (1) | unknown | 55 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502122 / 20855391 | Failed | 1 | RESULT discover-shell-error line=12 rc=1 | unknown | 45 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；归档日志直接观察 |
| 23502130 / 20855397 | Failed | 2 | RESULT find-pp-fail=declared-files-not-found | 环境假设 | 116 | unknown：无独立起止 | 声明赝势文件未找到，源脚本以exit2明确拒绝 |
| 23502136 / 20855402 | Failed | 124 | Program exception, exit code  (124) | 时限 | 284 | unknown：无独立起止 | 仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502146 / 20855412 | Finished | unknown | —（Finished） | 成功 | 63 | — | Finished；不存在失败归因 |
| 23502155 / 20855421 | Failed | 2 | Traceback (most recent call last): | 环境假设 | 40 | unknown：无独立起止 | 归档日志直接观察 |
| 23502195 / 20855461 | Failed | 124 | RESULT structure-deps-shell-error line=6 rc=124 | 时限 | 177 | unknown：无独立起止 | 归档日志直接观察 |
| 23502227 / 20855491 | Failed | 3 | 几何检查geometry_pass为false，入口明确exit3 | 科学设置 | 42 | unknown：无独立起止 | 冻结lisi_i41a2_check.py明确绑定geometry_pass与退出3；属于几何候选不满足检查 |
| 23502230 / 20855494 | Failed | 3 | 几何检查geometry_pass为false，入口明确exit3 | 科学设置 | 52 | unknown：无独立起止 | 同类几何检查拒绝；不是平台故障 |
| 23502232 / 20855496 | Failed | 3 | 几何检查geometry_pass为false，入口明确exit3 | 科学设置 | 85 | unknown：无独立起止 | 同类几何检查拒绝；不是平台故障 |
| 23502234 / 20855497 | Finished | unknown | —（Finished） | 成功 | 45 | — | Finished；不存在失败归因 |
| 23502254 / 20855516 | Failed | 127 | lisi_resource_scf.sh:77 /usr/bin/time: No such file or directory | 环境假设 | 44 | unknown：无独立起止 | 归档out.zip/scf.stderr直接确认缺命令 |
| 23502265 / 20855527 | Finished | unknown | —（Finished） | 成功 | 45 | — | Finished；不存在失败归因 |
| 23502266 / 20855528 | Finished | unknown | —（Finished） | 成功 | 323 | — | Finished；不存在失败归因 |
| 23502296 / 20855558 | Finished | unknown | —（Finished） | 成功 | 2187 | — | Finished；不存在失败归因 |
| 23502312 / 20855574 | Failed | 143 | RESULT lisi-resource-shell-error line=91 rc=143 | unknown | 2824 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；归档日志直接观察 |
| 23502313 / 20855575 | Finished | unknown | —（Finished） | 成功 | 174 | — | Finished；不存在失败归因 |
| 23502314 / 20855576 | Failed | 1 | RESULT reference-end phase=Si exit=143；缺running_scf.log | 时限 | 2744 | unknown：无独立起止 | 归档脚本timeout --preserve-status 2700和2744秒平台时长、exit143相符；缺日志是伴随现象，确切终止来源仍未独立证明 |
| 23502436 / 20855696 | Failed | 1 | Program exception, exit code  (1) | unknown | 173 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502449 / 20855709 | Failed | 1 | Traceback (most recent call last): | 环境假设 | 45 | unknown：无独立起止 | 归档日志直接观察 |
| 23502468 / 20855728 | Finished | unknown | —（Finished） | 成功 | 633 | — | Finished；不存在失败归因 |
| 23502469 / 20855729 | Failed | 3 | 分区电荷校验pass=false，退出3 | 科学设置 | 196 | unknown：无独立起止 | 归档标准输出的守恒/原子一致性检查拒绝；不能仅靠静态语法防止 |
| 23502538 / 20855797 | Failed | 134 | ABACUS Signal: Aborted (6)；K点文件缺偏移警告 | unknown | 63 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；归档scf.stderr确认abort；warning.log缺K点偏移，与abort的因果未证明，不记作时限 |
| 23502540 / 20855798 | Failed | unknown | remote/si_cell_relax_from_ion2.sh: line 10: unzip: command not found | 环境假设 | 47 | unknown：无独立起止 | 归档日志直接观察 |
| 23502545 / 20855804 | Failed | 2 | python3: can't open file extract_terminal_state.py: [Errno 2] No such file or directory | 环境假设 | 748 | unknown：无独立起止 | 归档out.zip/evidence/terminal_state.stderr确认未打包入口；不将源命令内timeout字样判成超时 |
| 23502546 / 20855805 | Finished | unknown | —（Finished） | 成功 | 320 | — | Finished；不存在失败归因 |
| 23502552 / 20855811 | Failed | 1 | Traceback (most recent call last): | 环境假设 | 41 | unknown：无独立起止 | 归档日志直接观察 |
| 23502553 / 20855812 | Failed | 1 | Traceback (most recent call last): | 脚本错误 | 33 | unknown：无独立起止 | 归档日志直接观察 |
| 23502558 / 20855817 | Finished | unknown | —（Finished） | 成功 | 111 | — | Finished；不存在失败归因 |
| 23502559 / 20855818 | Finished | unknown | —（Finished） | 成功 | 117 | — | Finished；不存在失败归因 |
| 23502560 / 20855819 | Finished | unknown | —（Finished） | 成功 | 127 | — | Finished；不存在失败归因 |
| 23502561 / 20855820 | Finished | unknown | —（Finished） | 成功 | 108 | — | Finished；不存在失败归因 |
| 23502562 / 20855821 | Failed | unknown | remote/static_120ry_density.sh: line 13: unzip: command not found | 环境假设 | 222 | unknown：无独立起止 | 归档日志直接观察 |
| 23502588 / 20855847 | Failed | 1 | Program exception, exit code  (1) | unknown | 38 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502592 / 20855851 | Finished | unknown | —（Finished） | 成功 | 59 | — | Finished；不存在失败归因 |
| 23502607 / 20855866 | Failed | 1 | Program exception, exit code  (1) | unknown | 44 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502608 / 20855867 | Finished | unknown | —（Finished） | 成功 | 1431 | — | Finished；不存在失败归因 |
| 23502646 / 20855908 | Finished | unknown | —（Finished） | 成功 | 184 | — | Finished；不存在失败归因 |
| 23502648 / 20855910 | Failed | 1 | Traceback (most recent call last): | unknown | 67 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；归档日志直接观察 |
| 23502658 / 20855921 | Finished | unknown | —（Finished） | 成功 | 307 | — | Finished；不存在失败归因 |
| 23502670 / 20855934 | Failed | unknown | remote/static_k_sigma_new.sh: line 13: /opt/csenv/bin/python: No such file or directory | 环境假设 | 158 | unknown：无独立起止 | 归档日志直接观察 |
| 23502675 / 20855939 | Failed | 1 | cp: cannot stat '/home/input_lbg-90229-23502675/static_k_sigma/${phase}_120Ry.STRU': No such file or directory | 脚本错误 | 992 | unknown：无独立起止 | 归档日志直接观察 |
| 23502690 / 20855952 | Failed | 143 | Program exception, exit code  (143) | unknown | 704 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502759 / 20856020 | Finished | unknown | —（Finished） | 成功 | 624 | — | Finished；不存在失败归因 |
| 23502760 / 20856021 | Failed | 143 | Program exception, exit code  (143) | unknown | 971 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23502761 / 20856022 | Finished | unknown | —（Finished） | 成功 | 168 | — | Finished；不存在失败归因 |
| 23502763 / 20856023 | Finished | unknown | —（Finished） | 成功 | 475 | — | Finished；不存在失败归因 |
| 23502764 / 20856025 | Finished | unknown | —（Finished） | 成功 | 636 | — | Finished；不存在失败归因 |
| 23502780 / 20856042 | Finished | unknown | —（Finished） | 成功 | 89 | — | Finished；不存在失败归因 |
| 23502801 / 20856062 | Finished | unknown | —（Finished） | 成功 | 176 | — | Finished；不存在失败归因 |
| 23502804 / 20856065 | Finished | unknown | —（Finished） | 成功 | 92 | — | Finished；不存在失败归因 |
| 23502854 / 20856087 | Finished | unknown | —（Finished） | 成功 | 113 | — | Finished；不存在失败归因 |
| 23502960 / 20856186 | Finished | unknown | —（Finished） | 成功 | 78 | — | Finished；不存在失败归因 |
| 23502993 / 20856203 | Finished | unknown | —（Finished） | 成功 | 70 | — | Finished；不存在失败归因 |
| 23502998 / 20856231 | Finished | unknown | —（Finished） | 成功 | 105 | — | Finished；不存在失败归因 |
| 23503000 / 20856233 | Finished | unknown | —（Finished） | 成功 | 68 | — | Finished；不存在失败归因 |
| 23503238 / 20856436 | Finished | unknown | —（Finished） | 成功 | 66 | — | Finished；不存在失败归因 |
| 23503295 / 20856528 | Finished | unknown | —（Finished） | 成功 | 97 | — | Finished；不存在失败归因 |
| 23503298 / 20856532 | Finished | unknown | —（Finished） | 成功 | 94 | — | Finished；不存在失败归因 |
| 23503322 / 20856555 | Finished | unknown | —（Finished） | 成功 | 98 | — | Finished；不存在失败归因 |
| 23504906 / 20858086 | Failed | 1 | Traceback (most recent call last): | 脚本错误 | 178 | unknown：无独立起止 | 归档日志直接观察 |
| 23506181 / 20859364 | Finished | unknown | —（Finished） | 成功 | 107 | — | Finished；不存在失败归因 |
| 23507120 / 20860349 | Failed | unknown | /home/input_lbg-90229-23507120/lbg-90229-23507120.sh: line 1: unzip: command not found | 环境假设 | 263 | unknown：无独立起止 | 归档日志直接观察 |
| 23507401 / 20860634 | Failed | 1 | Traceback (most recent call last): | 环境假设 | 45 | unknown：无独立起止 | 归档日志直接观察 |
| 23507410 / 20860643 | Failed | 1 | /opt/mamba/bin/python3: can't open file '/home/input_lbg-90229-23507410/unpacked/remote/periodic_voronoi_charge_new.py': [Errno 2] No such file or directory | 环境假设 | 55 | unknown：无独立起止 | 归档日志直接观察 |
| 23507423 / 20860657 | Failed | 1 | Program exception, exit code  (1) | unknown | 49 | unknown：无独立起止 | 已检查可用归档/冻结输入，现有日志只有泛化退出/结果未达门槛，不能确认根因；仅平台退出码/无可定位的错误日志；不能推定具体失败原因 |
| 23507424 / 20860658 | Finished | unknown | —（Finished） | 成功 | 135 | — | Finished；不存在失败归因 |
| 23507427 / 20860659 | Finished | unknown | —（Finished） | 成功 | 118 | — | Finished；不存在失败归因 |
| 23507438 / 20860672 | Finished | unknown | —（Finished） | 成功 | 54 | — | Finished；不存在失败归因 |

## 汇总与可防止范围

{'unknown': 11, '环境假设': 12, '时限': 3, '成功': 36, '科学设置': 4, '脚本错误': 3}

| 修复 | 对应失败Job | 数量 | 结论 |
|---|---|---:|---|
| 镜像包事实/预装ase、numpy、spglib | 23502155,23502449,23502552,23507401 | 4 | 可在提交前因缺包事实拒绝；不是本地装包就算远端验证 |
| 命令事实（unzip、/usr/bin/time、Python路径） | 23502254,23502540,23502562,23502670,23507120 | 5 | 同镜像命令/路径探测能拒绝明确缺项 |
| 输入/入口/赝势路径与未展开变量 | 23502130,23502545,23502675,23507410 | 4 | 明确缺输入可预防；动态生成路径必须登记/在执行点验证 |
| 禁Job联网下载/安装 | 23502136,23502195,23507423 | 3 | 入口包含clone/pip，改为构建期预置或沙箱；23507423只有通用exit1，根因仍unknown |
| 后处理脚本生命周期与健壮解析 | 23502553,23504906 | 2 | StopIteration/关闭ZIP后使用；静态语法预检不能保证防止 |
| 科学几何/分区校验、ABACUS设置 | 23502227,23502230,23502232,23502469 | 4 | 属于真实科学失败/候选拒绝；不能承诺用模板消除 |

前四组互不重叠，共16个失败Job具有可在提交前暴露的配置/网络风险，属于候选可避免上限，不宣称已真实重跑消除16次。W3须逐类测试结构性拦截。其余失败保持真实结果及unknown；exit143不能凭数字单独证明平台时限，退出码134和日志中的timeout命令也不能直接归因为超时。产物未回传是部分检索记录的伴随问题，不将已回传的失败Job改称只丢产物。
