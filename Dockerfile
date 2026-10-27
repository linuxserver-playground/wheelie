# syntax=docker/dockerfile:1

# Builds wheels for one distro and arch. Only the artifacts stage is exported (--output type=local), so no
# image is pushed anywhere. See scripts/build.sh.
ARG BASE=ghcr.io/linuxserver-playground/baseimage-alpine:3.24

FROM ${BASE} AS builder

ARG PACKAGES
ARG FIND_LINKS

# grpcio build args
ARG GRPC_BUILD_WITH_BORING_SSL_ASM=false
ARG GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=true
ARG GRPC_PYTHON_BUILD_WITH_CYTHON=true
ARG GRPC_PYTHON_DISABLE_LIBC_COMPATIBILITY=true

RUN \
  echo "**** Installing dependencies ****" && \
  if [ -f /usr/bin/apt ]; then \
    echo "**** Detected Ubuntu ****" && \
    apt-get update && \
    apt-get install --no-install-recommends -y \
      cargo \
      cmake \
      g++ \
      git \
      libffi-dev \
      libglib2.0-dev \
      libjpeg-dev \
      libssl-dev \
      libwebp-dev \
      libxml2-dev \
      libxslt1-dev \
      make \
      python3-dev \
      python3-pip \
      python3-venv \
      zlib1g-dev; \
  else \
    echo "**** Detected Alpine ****" && \
    apk add --no-cache --virtual=build-dependencies \
      cargo \
      cmake \
      g++ \
      gcc \
      geos-dev \
      git \
      glib-dev \
      jpeg-dev \
      libffi-dev \
      libwebp-dev \
      libxml2-dev \
      libxslt-dev \
      make \
      openssl-dev \
      py3-pip \
      python3-dev \
      zlib-dev; \
  fi && \
  python3 -m venv /lsiopy

COPY scripts/lib.sh scripts/build-wheels.sh /wheelie/

RUN /wheelie/build-wheels.sh

FROM scratch AS artifacts

COPY --from=builder /build /
