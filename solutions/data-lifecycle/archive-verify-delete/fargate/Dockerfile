# Build from the repository root so that shared/ is in the context:
#   docker build --platform linux/arm64 \
#     -f solutions/data-lifecycle/archive-verify-delete/fargate/Dockerfile -t <ecr-repo>:<tag> .
FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

COPY solutions/data-lifecycle/archive-verify-delete/fargate/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY shared/ /app/shared/
RUN rm -rf /app/shared/tests /app/shared/fpolicy-server /app/shared/cfn /app/shared/lambdas
COPY solutions/data-lifecycle/archive-verify-delete/fargate/entrypoint.py /app/entrypoint.py

RUN useradd --system --uid 10001 archive
USER 10001
ENTRYPOINT ["python", "/app/entrypoint.py"]
