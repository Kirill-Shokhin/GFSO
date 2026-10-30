# The image a delegated session works in when the installation declares nothing of its own: `gfso setup` builds it
# from this file and declares it as the execution "default" (data/executions.json). It carries no credential and no
# agent state — the model is reached through the system's door, the state is mounted per place.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
# git and git-lfs: the place's repository and the system's checkouts; python3: the system's own programs in the place
# and its door and gateway; iptables: the switch on the way out (`ContainerExecution`, mode open)
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils ca-certificates curl git git-lfs procps iptables \
        build-essential python3 python3-pip python3-venv python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# the CLI refuses to skip its permissions as root: the agent is an ordinary user, the uid the system's mounts expect
RUN useradd -m -u 1001 -s /bin/bash agent
USER agent
ENV HOME=/home/agent PATH=/home/agent/.local/bin:$PATH
# pinned: the image is named by this file, so what it installs is this file's too
ARG CLAUDE_VERSION=2.1.314
RUN curl -fsSL https://claude.ai/install.sh | bash -s "$CLAUDE_VERSION" && claude --version
RUN git config --global user.name gfso-agent && git config --global user.email gfso-agent@gfso.local
ENV CLAUDE_CONFIG_DIR=/home/agent/.claude PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
# a call with no directory of its own starts where the commands' listener — root holding no file capability — may enter
WORKDIR /
