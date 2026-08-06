# Office file → PDF conversion Lambda (Container Image)
# Converts docx/xlsx/pptx to PDF using LibreOffice headless.
# Referenced by docs/office-preview-design.md as approach "A".
#
# STATUS: builds, but is not wired into the backend. The portal currently ships
# approach "D" from that document — client-side rendering with docx-preview,
# which is why docx-preview is a package.json dependency and FilePreview.tsx
# renders in the browser. This image is the starting point if server-side
# conversion is ever needed for the formats the browser cannot handle (xlsx,
# pptx). No DockerImageFunction references it yet.
#
# ARCHITECTURE: x86_64 only. Upstream publishes no arm64 variant, because
# LibreOffice does not support it. Every other Lambda in this repository is
# arm64, so wiring this one up means an explicit
# `architecture: lambda.Architecture.X86_64` on just this function — it cannot
# inherit the default.
#
# Build locally on an arm64 machine with:
#   docker build --platform linux/amd64 -t office-convert .
#
# Size: ~877 MB (LibreOffice 26.2 + CJK fonts), well past the 250 MB layer
# limit, which is why this is a container image rather than a layer.
#
# Previously this file installed LibreOffice with `dnf install libreoffice-core`
# on top of the AWS Lambda Python base image. That never worked: the AL2023
# Lambda repositories do not carry LibreOffice, so the build failed with
# "No package matches 'libreoffice-core'" on both python:3.12 and python:3.13.
# Nothing referenced the file, so CI never surfaced it.
FROM public.ecr.aws/shelf/lambda-libreoffice-base:26.2-python3.13-x86_64

# Required by the base image. LibreOffice writes a per-user profile on first
# run, and the Lambda filesystem is read-only apart from /tmp — without this it
# exits with "The application cannot be started. User installation could not be
# completed." handler.py does not set it, so it belongs here.
ENV HOME=/tmp

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler
COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
