---
id: csup08_lean_environment
title: Bohrium Lean 4.32.2 与 Mathlib 固定环境
scope: global
status: candidate
evidence_status: hypothesis
kind: procedure
audience: both
tags:
- Lean
- Mathlib
- 环境
applicability: Lean 证明、数学库依赖与固定验证器
evidence_refs:
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:environments/lean-4.32.2/Dockerfile#sha256=d1d41647f415b7ed50124d663b702267972702dc6eec40c11e5c24054d9d0e1e
- file:environments/lean-4.32.2/environment.json#sha256=e92691ca69662e5e23754eeacbae4f9866549cb959e62841a0c07f6f1726aff0
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/job_input/prepare.sh#sha256=52ae64da88fbafc20bfe2d3c5023fbd9313ea046a9c7501e2c4c70845763d658
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/sandbox_compile_rootfixed.sh#sha256=5c84ec1ddb27c6ba55653bf858903b083ac8b261be604e4c4afe295ddfcf0abe
---
先复用已登记且身份符合的环境；没有环境时在授权 Bohrium 沙箱中准备，冒烟通过后才交给 Job。固定 Lean 4.32.2，Mathlib revision 905b95818eb32af7874a58b427f50c1711a5e96c；Lean 官方 tar.zst SHA256 为 5f2069e6f5db73780f374ccb49ce8ea649aa20a0cebf0116816744c999ce72aa。

授权远程环境中执行：
```bash
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl git zstd libgmp-dev time
mkdir -p /opt/cs-lean
curl -fL --connect-timeout 15 --max-time 240 https://github.com/leanprover/lean4/releases/download/v4.32.2/lean-4.32.2-linux.tar.zst -o /tmp/lean.tar.zst
echo '5f2069e6f5db73780f374ccb49ce8ea649aa20a0cebf0116816744c999ce72aa  /tmp/lean.tar.zst' | sha256sum -c -
tar --zstd -xf /tmp/lean.tar.zst --strip-components=1 -C /opt/cs-lean
git init /opt/cs-mathlib
git -C /opt/cs-mathlib remote add origin https://github.com/leanprover-community/mathlib4.git
git -C /opt/cs-mathlib fetch --depth 1 origin 905b95818eb32af7874a58b427f50c1711a5e96c
git -C /opt/cs-mathlib checkout --detach FETCH_HEAD
export PATH=/opt/cs-lean/bin:$PATH
lean --version
git -C /opt/cs-mathlib rev-parse HEAD
cd /opt/cs-mathlib
lake exe cache get
```
缓存下载不通时，换成同版本已核验的公开工具链与 Mathlib 依赖快照，转运后先核对每个文件哈希；不要把重试窗口耗光。项目验证时明确 lean --root、LEAN_PATH，包含 Mathlib 及 .lake/packages/*/.lake/build/lib/lean。先用极小的公开 import 文件编译冒烟，再运行题目验证器。

历史 v3 两个 Lean Run 实际完成了固定环境和编译；首轮权限故障与第二轮 curl/cache 失败仍保留。上面官方安装配方不是缓存网络长期可用的保证，成功环境依赖转运恢复，当前可复用镜像必须另有回执。

证据引用：
- file:docs/EVAL_V3_2026-10.md#sha256=340fa876722db2415b89148873ece6a5b21ab271aa7a87372f45292325ec2c05
- file:environments/lean-4.32.2/Dockerfile#sha256=d1d41647f415b7ed50124d663b702267972702dc6eec40c11e5c24054d9d0e1e
- file:environments/lean-4.32.2/environment.json#sha256=e92691ca69662e5e23754eeacbae4f9866549cb959e62841a0c07f6f1726aff0
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/job_input/prepare.sh#sha256=52ae64da88fbafc20bfe2d3c5023fbd9313ea046a9c7501e2c4c70845763d658
- file:workspace/runs/run_8eeef876cb/trials/trial_b6c5ab3d7a/sandbox_compile_rootfixed.sh#sha256=5c84ec1ddb27c6ba55653bf858903b083ac8b261be604e4c4afe295ddfcf0abe
