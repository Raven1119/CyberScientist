FROM registry.dp.tech/dptech/ubuntu:ubuntu24.04-py3.12
ENV UV_PYTHON_INSTALL_DIR=/opt/cs-python
RUN python3 -m pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple uv==0.9.15 && uv python install 3.11.14 && uv venv /opt/csenv --python 3.11.14
RUN uv pip install --python /opt/csenv/bin/python --index-url https://mirrors.aliyun.com/pypi/simple numpy==2.2.6 scipy==1.15.3 pandas==2.2.3 matplotlib==3.10.3 sympy==1.14.0 mpmath==1.3.0 numba==0.61.2 h5py==3.13.0 scikit-learn==1.6.1 networkx==3.4.2 pillow==11.2.1
ENV PATH=/opt/csenv/bin:$PATH
RUN uv pip freeze --python /opt/csenv/bin/python > /opt/cs-environment.lock
