FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
	 && apt-get install -y --no-install-recommends \
		 ca-certificates \
		 curl \
		 tar \
		 bash \
		 sudo \
		 python3 \
		 python3-pip \
		 cmake \
		 gcc-arm-none-eabi \
		 libnewlib-arm-none-eabi \
		 libstdc++-arm-none-eabi-newlib \
		 build-essential \
		 git \
	 && rm -rf /var/lib/apt/lists/*

# Create a non-root user to own /opt/wonderful as requested by the toolchain
ARG USERNAME=builder
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd -g ${USER_GID} ${USERNAME} || true \
	&& useradd -m -u ${USER_UID} -g ${USER_GID} -s /bin/bash ${USERNAME} || true

# Prepare /opt/wonderful and give ownership to the non-root user
RUN mkdir -p /opt/wonderful \
	&& chown -R ${USERNAME}:${USERNAME} /opt/wonderful

WORKDIR /home/${USERNAME}

# Download and extract the wonderful bootstrap as the non-root user
USER ${USERNAME}
ENV WF_BOOTSTRAP_URL="https://wonderful.asie.pl/bootstrap/wf-bootstrap-x86_64.tar.gz"
RUN curl -L "$WF_BOOTSTRAP_URL" -o /home/${USERNAME}/wf-bootstrap-x86_64.tar.gz \
	&& cd /opt/wonderful \
	&& tar xzvf /home/${USERNAME}/wf-bootstrap-x86_64.tar.gz

# Update wf-pacman and install wf-tools as the non-root user (auto-accept prompts)
# RUN yes | /opt/wonderful/bin/wf-pacman -Syu wf-tools
RUN /opt/wonderful/bin/wf-pacman -Syu --noconfirm wf-tools


# Expose the toolchain environment for all shells by sourcing wf-env
USER root
RUN echo '. /opt/wonderful/bin/wf-env' > /etc/profile.d/wonderful.sh \
	&& chmod 0644 /etc/profile.d/wonderful.sh

# Run toolchain setup steps as the non-root user. Each RUN sources wf-env
# so wf-* commands have the correct environment.
USER ${USERNAME}
# Use bash -lc so that wf-env is sourced with a supported shell
RUN bash -lc "source /opt/wonderful/bin/wf-env && /opt/wonderful/bin/wf-pacman -Syu --noconfirm wf-tools"
RUN bash -lc "source /opt/wonderful/bin/wf-env && /opt/wonderful/bin/wf-config repo enable blocksds"
RUN bash -lc "source /opt/wonderful/bin/wf-env && /opt/wonderful/bin/wf-pacman -Syu --noconfirm"
RUN bash -lc "source /opt/wonderful/bin/wf-env && /opt/wonderful/bin/wf-pacman -S --noconfirm blocksds-toolchain toolchain-llvm-teak-llvm"

# Create a stable shortcut for blocksds in /opt (do this as root)
USER root
RUN ln -sfn /opt/wonderful/thirdparty/blocksds /opt/blocksds || true


# Install Microsoft's package feed and the .NET 9 SDK
RUN set -eux; \
		curl -fsSL "https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb" -o /tmp/packages-microsoft-prod.deb; \
		dpkg -i /tmp/packages-microsoft-prod.deb; \
		rm -f /tmp/packages-microsoft-prod.deb; \
		apt-get update; \
		apt-get install -y --no-install-recommends dotnet-sdk-9.0; \
		rm -rf /var/lib/apt/lists/*;

ENV PATH="/opt/wonderful/bin:${PATH}"
ENV DLDITOOL="/opt/wonderful/thirdparty/blocksds/core/tools/dlditool/dlditool"

WORKDIR /dspico
