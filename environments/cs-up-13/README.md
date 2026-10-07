# CS-UP-13 材料环境与 ABACUS 冒烟

配方和脚本属于基础设施验证，科学计算均在 Bohrium 完成。私有镜像配方见 materials.Dockerfile，固定版本见 materials.pins.json。材料镜像在真实 Job 与沙箱中验证 Si 对称性、pymatgen 结构和 Cu EMT 有限能量；这不验证 DFT 精度。

将 materials-smoke.py 上传至 Job，使用 /opt/csenv/bin/python materials-smoke.py。Job 20845219 退出0，运行130秒；沙箱执行7.872秒，其中计算0.0197秒。五模块版本均与 pins 一致。首次镜像准备失败记录保留。

ABACUS 使用官方镜像 registry.dp.tech/davinci/abacus-source-code:20260717010446；上传 abacus-si-smoke.sh，执行 bash abacus-si-smoke.sh。v3.11.0-beta6，源码31c899d33，Si UPF来自镜像内 source_estate/test/support/Si_ONCV_PBE-1.0.upf，SHA256 481a5fae1167fd712d4e8e2e4df33f8bfc1e7d2abbc0565290d39fbba9dccb41。PW 基组无需数值轨道文件。30 Ry、2×2×2 k点仅用于通路冒烟。

首个 Job 20845220 的 SCF 实际收敛，但脚本匹配错误标记导致退出1；修正为真实 #SCF IS CONVERGED# 后，独立 Job 20847482 退出0，运行92秒，SCF约0.67秒、能量−211.9057192129556 eV。输入、输出和两次回执均保留在忽略目录 .package-checks/cs-up-13/。

ABACUS 沙箱创建成功于2026-10-07T21:06:52Z，但两次exec均TLS handshake timeout，不能声称沙箱冒烟通过；已登记通过Job验证的环境，known_issues说明此限制。材料沙箱创建成功于19:30:36Z。创建时间是观察，缓存有效期和重预热间隔unknown。
