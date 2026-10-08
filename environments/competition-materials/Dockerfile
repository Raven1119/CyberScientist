FROM registry.dp.tech/davinci/abacus-source-code:20260717010446
RUN apt-get update && apt-get install -y --no-install-recommends python3-venv unzip time ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/science && /opt/science/bin/python -m pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple pip==25.1.1 && /opt/science/bin/python -m pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple numpy==1.26.4 scipy==1.15.3 numba==0.61.2 ase==3.26.0 pymatgen==2025.5.28 spglib==2.6.0 phonopy==2.39.0 pybader==0.3.12 dpdata==0.2.25
RUN /opt/science/bin/python -m pip freeze > /opt/science/requirements.lock
ENV PATH=/opt/science/bin:$PATH
ENV OMP_NUM_THREADS=1
