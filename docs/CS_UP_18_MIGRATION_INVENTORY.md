# 比赛迁移前依赖清单

此清单在比赛目录创建前填写；实际迁移后的哈希、条数和检查结果追加到证据，不以计划代替完成。源配置/DB路径逐列扫描结果保存在私有cs18-premigration-path-inventory.json；秘密只比较数量/哈希，不写正文。

| 项目 | 现在的位置 | 比赛目录中的位置 | 怎么验证 |
|---|---|---|---|
| Codex0.161 Linux原生运行时 | 开发.package-checks/cs-up-13/codex-0.161.0/wheel/codex_cli_bin/bin/codex；当前执行者设置仍指0.159.3 | .runtime/bin/codex-0.161.0，PI和执行者均显式配置 | 二进制SHA、--version、真实两角色模型/effort/priority握手及登录 |
| 官方Playground CLI0.1.40 | tools/playground-cli/0.1.40/dist及integrity.json | 同相对路径，保留官方字节 | 全SHA、--version、旧题官方试构建；不提交 |
| bohr现代与兼容CLI | .cyberscientist/tools/wenyon-local/bohr-2.7.8；全局.bohrium/bohr | .runtime/bin及比赛私有wenyon home，设置重写 | 版本/二进制SHA、只读quota、授权沙箱创建与回收 |
| 应用Python环境 | 开发.venv；uv.lock | 比赛目录新建.venv，按uv.lock冻结安装，禁止复制开发venv | 安装日志、锁SHA、sys.executable/sys.path及隐藏源目录下启动 |
| 全栈客户端Python环境 | .cyberscientist/toolchain-venv | 比赛目录新建同相对环境，按fullstack-clients.requirements.lock安装 | dflow/bohrium实际import及固定版本，路径独立 |
| Node与前端 | Linux用户工具目录；apps/web源码/构建 | 只发布指定提交构建的apps/web/dist；Node为操作系统依赖 | 生产构建、前端HTTP、WebBridge实际打开；隐藏开发目录后仍可访问 |
| 设置全部绝对路径 | app.data_dir、brain/executor.executable、playground.cli_executable、bohrium.executable/wenyon_executable/wenyon_home、memory.root共8项 | 对应比赛位置 | 对设置递归扫描绝对路径；禁止活动配置保留开发路径 |
| SQLite | .cyberscientist/cyberscientist.db及WAL | .cyberscientist/cyberscientist.db | 停旧后端前完整一致备份，迁移后逐表计数、Run/提交/密钥数、自检/digest及历史前端 |
| DB活动路径/登记 | runtime_observations2列项、environment_catalog_entries5行，以及运行文件索引 | 比赛实际工具/环境/经验位置 | 行级迁移清单与活动查询全扫描为0；目录哈希/绑定调整保留旧版本依据 |
| DB历史路径例外 | runs旧快照、events10910行、checkpoints、review_requests、guidance、experience_contexts、旧评分/复盘/提交等 | 保留原始历史；单列例外及实际文件的归档映射 | 原证据哈希和行数不变，不改科学原文；历史页面可查看；新会话不注入这些开发路径 |
| .env与密钥 | 根.env、.cyberscientist/secrets.json、wenyon home；全局Codex auth/config/.env | 比赛忽略的私有文件，权限0600；登录凭据复制 | 数量/完整文件SHA前后核对；每账号/auth/me；不进Git，不打印值 |
| Codex配置和技能 | 全局config.toml完整6类配置键；当前启用23比赛技能含17bohrium | .runtime/codex完整复制相关配置后删除无关项目/原生技能；skills目录完整复制23技能，系统扫描只指比赛 | 登录、模型/提供商、priority/fast、功能开关、工具桥和技能名称/全目录SHA清单对照；原生帧零污染 |
| 启动脚本与PID | 开发start.sh、端口8765旧后端PID1321553；实际PID须停止前重新读取 | start-runtime.sh、.runtime/backend.pid；同端口由比赛后端接管 | 停旧后端并禁用开发启动/resume_on_startup，检查自启动登记和端口空闲；只允许一个后端 |
| 经验目录 | experience全库，含用户未跟踪现有内容与DB修订 | 比赛experience运行数据 | 完整备份/逐文件SHA；技术路径迁移保留原修订，不导入待审候选；后续发布前后修订不变 |
| 历史Run工作目录 | workspace/runs及关联冻结输入/输出 | 独立CyberScientist-run-archive归档根，与比赛workspace/runs分开 | 归档清单/大小/哈希、历史文件读取映射；新会话cwd必须比赛目录下 |
| 环境目录登记 | environment_catalog_entries/runtime_environments/image_facts | 比赛DB，已验证云镜像ID不变 | 保留实际镜像/版本/回执SHA，活动本地路径重写，能力索引逐条读取 |
| 版本和代码指纹 | Git工作树/HEAD，现有进程已加载版本可能不同 | .runtime/version.json及封存清单，无.git | 发布commit SHA、自检加载/磁盘一致、完整文件哈希；重部署和较早版本回退 |

外部操作系统依赖（Linux Python基础解释器、Node、CA、标准库）与开发目录依赖分别列出；隐藏依赖测试检查的是开发目录整体改名后的实际可运行性。两新账号凭据缺失保持阻塞，不能用复制其他凭据、额外注册或Regenerate来假装覆盖。
