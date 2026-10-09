---
name: cyberscientist-sandbox
description: Use the per-task resident Bohrium sandbox as the main workspace for debugging, smoke tests, post-processing and medium computations.
---

# 沙箱使用

本题常驻沙箱是主力工作场所：调试、冒烟、后处理和中等规模计算都在这里做。长时间、大规模计算才交给 Job（同一镜像）。

- 本题沙箱由系统在开局时按 PI 选定的镜像创建，信息见能力索引中的 topic-sandbox；寿命覆盖整场比赛，不必续期。
- 长命令用 background 启动，再用 poll 读取日志和退出码；短命令用 exec。每个 exec、files.write、background 都用稳定的 operation_id；回执丢失时先对账，不重复执行。
- **环境**：先从环境目录读配方并做冒烟（关键 import 加一次最小的实际操作），成功后用 research_environment 的 record_smoke 登记。不要假定镜像里有你需要的包，缺的就装。
- 文件只读写本 Trial 或本题工作目录；结果取回本地交付目录后再引用。
- 沙箱不可用（创建失败、到期）时，系统会回退到同镜像的 Job，并在事件中写明原因。
- GPU 需要单独授权。
