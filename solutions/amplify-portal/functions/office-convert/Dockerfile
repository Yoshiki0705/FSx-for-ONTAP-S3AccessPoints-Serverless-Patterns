# Office file → PDF conversion Lambda (Container Image)
# Converts docx/xlsx/pptx to PDF using LibreOffice headless.
# Used by UX-5 (Office file preview in portal).
#
# Build: docker build -t office-convert .
# Deploy: Push to ECR, reference in CDK as lambda.DockerImageFunction
#
# Size: ~500MB (LibreOffice + fonts) — exceeds 250MB Lambda Layer limit,
# hence using container Lambda (max 10GB).

FROM public.ecr.aws/lambda/python:3.12

# Install LibreOffice minimal + CJK fonts
RUN dnf install -y \
    libreoffice-core \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    google-noto-sans-cjk-ttc-fonts \
    && dnf clean all

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy handler
COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
