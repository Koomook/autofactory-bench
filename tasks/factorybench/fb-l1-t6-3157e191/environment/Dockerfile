# Agent environment: Python 3 with numpy and pandas. Harbor installs the agent CLI at setup.
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl bash procps python3 python3-numpy python3-pandas xz-utils ripgrep git \
 && rm -rf /var/lib/apt/lists/*
RUN ln -sf /usr/bin/python3 /usr/local/bin/python
WORKDIR /app
COPY data /app/data
COPY manual /app/manual
