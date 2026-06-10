FROM python:3.12-slim

WORKDIR /app

# 依存関係インストール
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコード
COPY backend/app ./app
COPY frontend ./frontend

# ヘルスチェック用
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
