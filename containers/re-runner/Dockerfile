ARG PYTHON_BASE_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

LABEL org.opencontainers.image.title="AgentKVM2USB reverse-engineering runner" \
      org.opencontainers.image.description="Headless USB trace and ARM firmware analysis utilities" \
      org.opencontainers.image.source="https://github.com/SemperSupra/AgentKVM2USB"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eux; \
    echo 'wireshark-common wireshark-common/install-setuid boolean false' | debconf-set-selections; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      bash \
      binutils-arm-none-eabi \
      ca-certificates \
      file \
      gdb-multiarch \
      jq \
      libusb-1.0-0 \
      p7zip-full \
      qemu-user \
      tini \
      tshark \
      unzip \
      usbutils \
      xz-utils \
      yara; \
    rm -rf /var/lib/apt/lists/*

# Python dependencies are hash-locked. requirements.in is the human-maintained
# input; requirements.lock.txt is the generated pip-compile lock with
# --require-hashes. The lock is platform-specific to the Linux Python 3.12 image.
COPY containers/re-runner/requirements.in /tmp/requirements.in
COPY containers/re-runner/requirements.lock.txt /tmp/requirements.lock.txt
RUN python3 -m pip install --no-cache-dir --require-hashes --requirement /tmp/requirements.lock.txt \
    && rm /tmp/requirements.in /tmp/requirements.lock.txt

RUN useradd --create-home --uid 1000 --shell /bin/bash analyst \
    && mkdir -p /work/input /work/output /work/projects /work/vendor \
    && chown -R analyst:analyst /work

WORKDIR /work
USER analyst
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash"]
