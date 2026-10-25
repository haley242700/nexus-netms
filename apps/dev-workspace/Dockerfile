FROM codercom/code-server:latest

USER root

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        docker.io \
        docker-compose-v2 \
        git \
        nodejs \
        npm \
        openssh-client \
        python3 \
        python3-pip \
        python3-venv \
        rsync \
    && rm -rf /var/lib/apt/lists/*
