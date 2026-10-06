# CS-UP-12 环境起点复现

这五份 Dockerfile 只使用公开 Bohrium 基础镜像与公开软件来源，不包含私有镜像地址、凭据或账号回执。它们是环境目录的起点；科研 Run 选用后仍须执行自己的恢复冒烟。

| 起点 | 入口与固定依赖 |
|---|---|
| sci-py | `/opt/csenv/bin/python`；Python 3.11.14、固定版本科学包 |
| torch-cpu | 同上；PyTorch 2.5.1 CPU |
| torch-cuda | 同上；PyTorch 2.5.1、CUDA 12.4 |
| pyscf | 同上；PySCF 2.8.0 |
| lean-mathlib | 先解压 `/opt/cs-lean-environment.tar.zst`，再用 `/opt/cs-lean/bin`；Lean 4.32.2、Mathlib `905b95818eb32af7874a58b427f50c1711a5e96c` |

Python 镜像使用公开 `registry.dp.tech/dptech/ubuntu:ubuntu24.04-py3.12`，uv 安装独立 Python 3.11.14。系统 Python 不等于科学包所在解释器；Job 必须写绝对入口，不能依赖启动器是否保留镜像 PATH。Lean 先在公开 Ubuntu 20.04 镜像完成编译，将整个工具链、工程及全部预编译产物打成 zstd 归档，然后与依赖清单一并复制到干净的公开 Ubuntu 24.04 镜像。恢复时先解压；编译缓存已随镜像提供，无需再下载。

软件源环境事实：Bohrium CPU Job 的实际探针确认 PyPI、阿里云、清华的 uv 索引、GitHub Lean 发布页、Python standalone 发布页、PyTorch CPU/cu121 索引均返回 200。原输出 SHA 为 `b1abc017229d6253d36112c7a24a7c311701504d8507911207f987b20e147c92`，回执只在本机忽略目录。Mathlib 缓存根路径返回 404，不能据此推断具体缓存文件不存在；随后实际 `lake exe cache get` 与完整构建通过。以上只代表 2026-10-06 的观察，7 天内或安装失败时重新核对；索引可达不保证大 wheel 下载稳定，原 CUDA 索引超时保留。

Dockerfile 固定直接依赖。四份 `*.requirements.lock` 是实际通过冒烟的环境完整版本清单，包括传递依赖；如需重建到相同传递版本，在安装后用对应清单同步，再做完整冒烟：

```bash
uv pip sync --python /opt/csenv/bin/python \
  --index-url https://mirrors.aliyun.com/pypi/simple \
  sci-py.requirements.lock
```

Torch CPU 清单还需 `--extra-index-url https://download.pytorch.org/whl/cpu`；严格按完整清单同步时使用 `--index-strategy unsafe-best-match`，从这两个公开来源匹配固定版本，避免 uv 的默认首个索引规则挡住传递依赖。参数依据见 [uv 官方索引说明](https://docs.astral.sh/uv/concepts/indexes/)。CUDA 清单从 PyPI 安装，不能把 CPU wheel 当 CUDA 环境。两份 Torch Dockerfile 初装 SymPy 1.14.0，Torch 依赖随后将其改为 1.13.1；最终版本以实际锁文件为准。这种完整清单同步是复现步骤，须另做冒烟，并非本卡提交 Dockerfile 的实际构建步骤。版本清单没有锁定上游基础镜像 digest 或软件源全部文件哈希，不声称按字节重现镜像。

用已认证 Linux bohr 2.7.8 的 v4 构建接口，并由调用者明确提供有权使用的项目 ID：

```bash
: "${BOHRIUM_PROJECT_ID:?请设置已授权项目ID}"
bohr image build --name cs12-sci-py-reproduction \
  --project-id "$BOHRIUM_PROJECT_ID" \
  --dockerfile environments/cs-up-12/sci-py.Dockerfile \
  --desc 'Pinned public scientific starting environment' \
  -y --no-interactive -o json
```

构建接受不等于构建成功；随后查询 `bohr image get <构建返回的ID> -o json`。新镜像在 Sandbox 返回 `IMAGE_PREPARATION_IN_PROGRESS` 时只对同 request-id 退避；普通未知创建先对账。创建、构建、Job 和 Sandbox 分别使用原有授权及平台额度。

Python 冒烟需要实际验证线性方程、符号行列式、DataFrame、Numba、HDF5 与 PNG 输出，Torch 另验证矩阵乘法及 CPU/GPU 状态，PySCF 另验证 H2 RHF 收敛。CUDA 12.4 在本卡 GPU Job 的 T4/驱动 580.105.08 以及 Sandbox 的 RTX 4090/驱动 570.124.06 上通过；其他 GPU 仍须核对目录、驱动和实际 CUDA 可用性。

Lean 的锁定依赖见 `lean-mathlib.pins.json`。恢复冒烟应在工程中运行完整 `lake build`，并设置失效代理证明不依赖再下载，随后编译一个使用 Mathlib 的证明：

```bash
if [ ! -f /opt/cs-lean-archive-restored ]; then
  tar --zstd -xf /opt/cs-lean-environment.tar.zst -C /
  touch /opt/cs-lean-archive-restored
fi
export PATH=/opt/cs-lean/bin:$PATH
cd /opt/cs-mathlib
HTTP_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 \
  ALL_PROXY=http://127.0.0.1:1 lake build
printf 'import Mathlib\nexample (n : Nat) : n + 0 = n := by simp\n' > /tmp/cs12-smoke.lean
lake env lean /tmp/cs12-smoke.lean
```

实际 Job/Sandbox 回执、完整输出和哈希只保存在本机忽略目录。脱敏耗时、失败原因、目录与前端验证结论见 [修复证据](../../docs/CS_UP_12_FIX_EVIDENCE.md)。

镜像构建完成后按同一镜像ID立即进行一次有界Sandbox预热，成功后只回收这次新建沙箱，不改已有资源。自检“各镜像沙箱创建时间”显示实际成功回执时间；image get的status2不代表Sandbox已准备。当前Lean建议8核32GiB，完整import Mathlib实测峰值约6.37GiB；先小模块再完整import，压缩归档解压实测62.415秒。平台缓存寿命/重预热周期unknown；约39分钟后再次创建仍约104秒，未见明显提速。重建产生新镜像ID后必须重新预热；无需为了超时反复重建。

真实明确准备拒绝的首末观察跨度：完整/干净/压缩Lean镜像314/431/221秒，均超过旧180秒。平台完整准备耗时unknown；维护环境观察保存回执SHA和区间，不能把构建完成时间当成准备完成时间。产品最长等待45分钟、单次请求240秒、最长间隔5分钟；普通超时先只读对账。
