FROM registry.dp.tech/dptech/dp/native/prod-88474/90229/cstwelve-sci-py-1791294064:latest
RUN apt-get update && apt-get install -y --no-install-recommends libopengl0 libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 && rm -rf /var/lib/apt/lists/*
RUN uv pip install --python /opt/csenv/bin/python --index-url https://mirrors.aliyun.com/pypi/simple ase==3.26.0 pymatgen==2025.5.28 spglib==2.6.0 phonopy==2.39.0 ovito==3.12.3
RUN uv pip freeze --python /opt/csenv/bin/python > /opt/cs-materials.lock
ENV QT_QPA_PLATFORM=offscreen
