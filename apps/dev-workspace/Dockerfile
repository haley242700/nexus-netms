FROM codercom/code-server:latest

USER root

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi

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
