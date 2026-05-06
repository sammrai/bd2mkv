# syntax=docker/dockerfile:1.6
ARG MAKEMKV_VERSION=1.18.3

FROM debian:bookworm-slim AS builder
ARG MAKEMKV_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config curl ca-certificates \
        libssl-dev libexpat1-dev zlib1g-dev libavcodec-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSL -o oss.tar.gz "https://www.makemkv.com/download/makemkv-oss-${MAKEMKV_VERSION}.tar.gz" \
 && curl -fsSL -o bin.tar.gz "https://www.makemkv.com/download/makemkv-bin-${MAKEMKV_VERSION}.tar.gz" \
 && tar xf oss.tar.gz && tar xf bin.tar.gz \
 && cd "makemkv-oss-${MAKEMKV_VERSION}" \
    && ./configure --disable-gui \
    && make -j"$(nproc)" \
    && make install DESTDIR=/out \
 && cd "../makemkv-bin-${MAKEMKV_VERSION}" \
    && mkdir -p tmp && echo accepted > tmp/eula_accepted \
    && make install DESTDIR=/out

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg mkvtoolnix \
        python3 python3-pip python3-venv \
        ca-certificates curl unzip bsdmainutils \
        libssl3 libexpat1 zlib1g libavcodec59 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/usr/ /usr/

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
RUN python3 -m venv "$VIRTUAL_ENV" \
 && pip install --no-cache-dir faster-whisper

COPY bd2mkv /usr/local/bin/bd2mkv
COPY lib/ /usr/local/lib/bd2mkv/
RUN chmod +x /usr/local/bin/bd2mkv

ENV KEYDB_CACHE=/var/cache/aacs/keydb.cfg \
    BETAKEY_CACHE=/var/cache/makemkv/beta.key \
    WHISPER_CACHE=/var/cache/whisper \
    BD2MKV_LIB=/usr/local/lib/bd2mkv

VOLUME ["/var/cache/aacs", "/var/cache/makemkv", "/var/cache/whisper"]
WORKDIR /work
ENTRYPOINT ["bd2mkv"]
CMD ["all"]
