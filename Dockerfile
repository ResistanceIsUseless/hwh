# hwh - Hardware Hacking Toolkit Docker Image
#
# Usage:
#   docker build -t hwh .
#   docker run -it --privileged -v /dev:/dev hwh
#
# For access to USB devices, you need --privileged or specific device mounts:
#   docker run -it --device=/dev/ttyUSB0 hwh

FROM python:3.11-slim

LABEL maintainer="ResistanceIsUseless"
LABEL description="Hardware Hacking Toolkit - Multi-device TUI for hardware security research"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    usbutils \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running hwh
RUN useradd -m -s /bin/bash hwh && \
    usermod -aG dialout hwh

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

# Install hwh
RUN pip install --no-cache-dir .

# Switch to non-root user
USER hwh

# Set terminal for TUI
ENV TERM=xterm-256color

# Default command - launch TUI
CMD ["hwh"]
