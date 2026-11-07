# The image a delegated session works in when the installation declares nothing of its own: `gfso setup` builds it
# from this file and declares it as the execution "default" (data/executions.json). It carries no credential and no
# agent state — the model is reached through the system's door, the state is mounted per place.
# what it is built on named here, the distribution's packages aside: the base by its digest, the CLI by its checksum — a tag and a live installer
# script were whatever their servers held at `gfso setup` (critic over the stream in use; the door runs this image too)
FROM ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852

ENV DEBIAN_FRONTEND=noninteractive
# git and git-lfs: the place's repository and the system's checkouts; python3: the system's own programs in the place
# and its door and gateway; iptables: the switch on the way out (`ContainerExecution`, mode open); nftables: the bound on
# the connections one container holds (`WayOut.seal`), which this kernel has for nft alone
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils ca-certificates curl git git-lfs procps iptables nftables \
        build-essential python3 python3-pip python3-venv python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

# the CLI refuses to skip its permissions as root: the agent is an ordinary user, the uid the system's mounts expect
RUN useradd -m -u 1001 -s /bin/bash agent
USER agent
ENV HOME=/home/agent PATH=/home/agent/.local/bin:$PATH
# pinned: the image is named by this file, so what it installs is this file's too — the CLI's own binary, fetched by
# its version and refused unless its checksum is the one written here, then set up by itself (as its installer does)
ARG CLAUDE_VERSION=2.1.314
ARG CLAUDE_SHA256_X64=4487042b4c4f5d88d4568f68ae98aae0b1ffae58864cf57fb868641bc5f84594
ARG CLAUDE_SHA256_ARM64=a66c0a8f5d0c87a439953d797985192bbcbaefbce2e0d7b2eaa8df30ef0f3ef2
RUN set -e; case "$(uname -m)" in x86_64) p=linux-x64 c=$CLAUDE_SHA256_X64;; aarch64) p=linux-arm64 c=$CLAUDE_SHA256_ARM64;;         *) echo "no pinned CLI for $(uname -m)" >&2; exit 1;; esac;     curl -fsSL -o /tmp/claude "https://downloads.claude.ai/claude-code-releases/$CLAUDE_VERSION/$p/claude";     echo "$c  /tmp/claude" | sha256sum -c -; chmod +x /tmp/claude; /tmp/claude install "$CLAUDE_VERSION"; rm -f /tmp/claude;     claude --version
RUN git config --global user.name gfso-agent && git config --global user.email gfso-agent@gfso.local
ENV CLAUDE_CONFIG_DIR=/home/agent/.claude PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
# a call with no directory of its own starts where the commands' listener — root holding no file capability — may enter
WORKDIR /
