# CS-UP-14 提交链路证据

阶段1的fallback-4已推送，阶段2只验证一道已结束LiSi题。
已取得并校验项目内官方CLI0.1.39，全局安装与配置未改。
已复核三种模型真实日志可转换，旧error事件转换缺陷仍存在。
不编辑原始记录，保留失败并使用新干净会话。
提交链路与真实Worker验收将在下文按实际结果追加。

## W0

D-73原文已入UPGRADE_DESIGN§5；阶段2最多一个Run、2实验+1收割，不启动其他题、彩排二或阶段4。

## W1

官方tarball121215字节，SHA256与latest.json及安装脚本声明一致，版本命令实际0.1.39。解包于忽略目录.package-checks/playground-cli-0.1.39，未改全局0.1.33。AgentMaster只读查看host/submission.py及169个command.json的参数和环境键；不能据本地命令记录声称所有评分有效。原始安装来源/历史Worker环境配置unknown。

真实Terra/Astra/DeepSeek原生日志分别106494/105663/25192133字节，官方转换9/8/902步，工具配对1/1、1/1、423/423；SHA前后不变。旧event流合成反例加一条error，2步变1条error，丢掉执行证据，0.1.39仍有缺陷。原文件不编辑；另一条干净原生会话是替代。CLI新包会加envelope/脱敏，因此系统已有封存包模式必须预先装入原生字节，避免CLI重新打包。参赛过程§6列出源码位置、命令模板和故障处理。

原始转换输出及输入哈希在.package-checks/cs-up-14/conversion-probes.json；没有把原生日志、令牌或第三方原始轨迹加入Git。
