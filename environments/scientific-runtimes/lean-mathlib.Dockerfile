FROM registry.dp.tech/dptech/ubuntu:20.04-py3.10 AS compiled
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git zstd libgmp-dev && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/cs-lean && curl -fL --connect-timeout 30 --max-time 1200 https://github.com/leanprover/lean4/releases/download/v4.32.2/lean-4.32.2-linux.tar.zst -o /tmp/lean.tar.zst && echo '5f2069e6f5db73780f374ccb49ce8ea649aa20a0cebf0116816744c999ce72aa  /tmp/lean.tar.zst' | sha256sum -c - && tar --zstd -xf /tmp/lean.tar.zst --strip-components=1 -C /opt/cs-lean && rm /tmp/lean.tar.zst
ENV PATH=/opt/cs-lean/bin:$PATH
RUN git init /opt/cs-mathlib && git -C /opt/cs-mathlib remote add origin https://github.com/leanprover-community/mathlib4.git && git -C /opt/cs-mathlib fetch --depth 1 origin 905b95818eb32af7874a58b427f50c1711a5e96c && git -C /opt/cs-mathlib checkout --detach FETCH_HEAD
RUN cd /opt/cs-mathlib && lean --version && lake exe cache get
RUN python3 -c 'import json, subprocess; from pathlib import Path; p=Path("/opt/cs-mathlib"); m=json.loads((p/"lake-manifest.json").read_text()); pins={x["name"]:x["rev"] for x in m["packages"]}; pins["mathlib"]=subprocess.check_output(["git","-C",str(p),"rev-parse","HEAD"],text=True).strip(); Path("/opt/cs-lean-environment.json").write_text(json.dumps({"schema":1,"lean_version":"4.32.2","lean_bin":"/opt/cs-lean/bin","mathlib_root":str(p),"mathlib_revision":pins["mathlib"],"packages":pins},sort_keys=True))'

RUN cd /opt/cs-mathlib && lake build

RUN tar --use-compress-program='zstd -T2 -3' -cf /tmp/cs-lean-environment.tar.zst -C / opt/cs-lean opt/cs-mathlib

FROM registry.dp.tech/dptech/ubuntu:ubuntu24.04-py3.12
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git libgmp10 zstd && rm -rf /var/lib/apt/lists/*
COPY --from=compiled /tmp/cs-lean-environment.tar.zst /opt/cs-lean-environment.tar.zst
COPY --from=compiled /opt/cs-lean-environment.json /opt/cs-lean-environment.json
