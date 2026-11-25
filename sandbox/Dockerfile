FROM ubuntu:24.04

# Tools the agent needs to compile and debug C code
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev valgrind gdb && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work
