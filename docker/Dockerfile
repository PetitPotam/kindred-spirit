# Her brain in a box (#128): her brain, the gateway, the dashboard, her voice (Kokoro) and her hearing (Whisper on
# the CPU), to run ON YOUR OWN COMPUTER with Docker (Windows, Linux). Nothing is hosted anywhere: the game connects to
# 127.0.0.1 as usual. How to use it: docker/README.md. Published as ghcr.io/petitpotam/kindred-spirit-brain with
# every release (.github/workflows/release.yml); built and tested on every pull request that touches it
# (.github/workflows/platforms.yml, scripts/test-install.sh docker).
#
#   docker build -f docker/Dockerfile -t kindred-spirit-brain .
#
# Base images and whisper.cpp are pinned exactly (digest, commit), so a changed tag can't change what's built.

# ---- whisper-server, built from whisper.cpp's source (portable: no CPU-specific instructions)
FROM ubuntu:24.04@sha256:2198e4c65076e9cb0b3d695219df667c0e3b0072da64ca3c2648aca17dcecaf5 AS whisper
RUN apt-get update \
 && apt-get install -y --no-install-recommends git cmake g++ make ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# whisper.cpp v1.9.5
ARG WHISPER_COMMIT=d1be6fde11ac6e0407606b4e42fe72d34add8037
RUN git init -q /src && cd /src \
 && git fetch -q --depth 1 https://github.com/ggml-org/whisper.cpp "$WHISPER_COMMIT" && git checkout -q FETCH_HEAD \
 && cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF \
      -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_SDL2=OFF \
 && cmake --build build -j"$(nproc)" --target whisper-server \
 && install -m 755 build/bin/whisper-server /usr/local/bin/whisper-server

# ---- her
FROM ubuntu:24.04@sha256:2198e4c65076e9cb0b3d695219df667c0e3b0072da64ca3c2648aca17dcecaf5
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv curl ca-certificates tini libgomp1 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=whisper /usr/local/bin/whisper-server /usr/local/bin/whisper-server
# one Python for her brain, her voice and her memory's embeddings (the Mac install keeps three)
COPY brain/requirements.txt /opt/kindred/brain/requirements.txt
RUN python3 -m venv /opt/kindred/venv \
 && /opt/kindred/venv/bin/pip install --no-cache-dir -q -r /opt/kindred/brain/requirements.txt \
      kokoro-onnx==0.6.1 soundfile==0.14.0 fastembed==0.9.1
COPY LICENSE /opt/kindred/LICENSE
COPY brain /opt/kindred/brain
COPY services /opt/kindred/services
COPY scripts /opt/kindred/scripts
COPY docker /opt/kindred/docker
# uid 1000, the first user on most Linux computers: the files she writes in your ~/.kindred-spirit are yours
# (scripts/docker-run.sh runs her as you when your uid is another one)
RUN userdel -r ubuntu 2>/dev/null; useradd --uid 1000 --create-home --home-dir /home/pip pip \
 && chmod 1777 /home/pip
ENV HOME=/home/pip \
    KINDRED_PYTHON=/opt/kindred/venv/bin/python \
    KINDRED_KOKORO_PYTHON=/opt/kindred/venv/bin/python \
    KINDRED_EMBED_PYTHON=/opt/kindred/venv/bin/python \
    KINDRED_RUN_DIR=/tmp/kindred-run \
    KINDRED_LISTEN=0.0.0.0 \
    KINDRED_DOCKER=1 \
    PYTHONDONTWRITEBYTECODE=1
USER pip
WORKDIR /opt/kindred
# 47811: the game talks to her brain; 11440: her dashboard (K in the game). Publish them on 127.0.0.1 only.
EXPOSE 47811 11440
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD curl -fs -o /dev/null http://127.0.0.1:11440/api/her || exit 1
ENTRYPOINT ["tini", "-g", "--", "bash", "/opt/kindred/docker/entrypoint.sh"]
