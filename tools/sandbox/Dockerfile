FROM python:3.13.7-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
RUN useradd -m -u 1000 agent
USER agent
RUN git config --global --add safe.directory /work && git config --global user.name agent && git config --global user.email agent@sandbox.invalid
WORKDIR /work
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GIT_CONFIG_NOSYSTEM=1
