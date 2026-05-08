#!/usr/bin/env python3
"""
SageMaker Serverless Inference テスト用モデルアーティファクト作成スクリプト

SageMaker sklearn コンテナが要求するディレクトリ構造で model.tar.gz を生成する。

構造:
  model.tar.gz
  ├── model.joblib          # sklearn モデル（ダミー分類器）
  └── code/
      └── inference.py      # カスタム推論ハンドラ

使用方法:
  python scripts/create_test_model.py [--output-dir ./test-data]
  python scripts/create_test_model.py --upload s3://bucket/path/

前提条件:
  pip install scikit-learn joblib numpy

注意:
  sklearn 公式コンテナ (~1.5GB) は Serverless Inference の 180 秒タイムアウトを
  超過する可能性が高い。本番環境では軽量カスタムコンテナ (<500MB) を推奨。
  本スクリプトはテスト・検証目的で使用する。
"""

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# inference.py テンプレート（model.tar.gz 内の code/ に配置）
# ---------------------------------------------------------------------------
INFERENCE_PY = '''\
"""
SageMaker sklearn コンテナ用カスタム推論ハンドラ。

SageMaker sklearn コンテナは model.tar.gz 内の code/inference.py を
自動的にロードし、以下の関数を呼び出す:
  - model_fn: モデルのデシリアライズ
  - input_fn: リクエストボディのデシリアライズ
  - predict_fn: 推論実行
  - output_fn: レスポンスのシリアライズ
"""

import json
import os

import joblib
import numpy as np


def model_fn(model_dir):
    """モデルをロードする。"""
    model_path = os.path.join(model_dir, "model.joblib")
    model = joblib.load(model_path)
    return model


def input_fn(request_body, request_content_type):
    """リクエストボディをデシリアライズする。"""
    if request_content_type == "application/json":
        data = json.loads(request_body)
        if isinstance(data, dict) and "instances" in data:
            return np.array(data["instances"])
        return np.array(data)
    elif request_content_type == "text/csv":
        lines = request_body.strip().split("\\n")
        return np.array([list(map(float, line.split(","))) for line in lines])
    else:
        raise ValueError(f"Unsupported content type: {request_content_type}")


def predict_fn(input_data, model):
    """推論を実行する。"""
    predictions = model.predict(input_data)
    probabilities = model.predict_proba(input_data)
    return {"predictions": predictions.tolist(), "probabilities": probabilities.tolist()}


def output_fn(prediction, accept):
    """レスポンスをシリアライズする。"""
    if accept == "application/json":
        return json.dumps(prediction), "application/json"
    raise ValueError(f"Unsupported accept type: {accept}")
'''


def create_dummy_model(model_path: Path) -> None:
    """ダミーの sklearn 分類モデルを作成する。"""
    try:
        from sklearn.datasets import make_classification
        from sklearn.ensemble import RandomForestClassifier

        import joblib
    except ImportError:
        print("ERROR: scikit-learn と joblib が必要です。")
        print("  pip install scikit-learn joblib numpy")
        sys.exit(1)

    print("  ダミー分類モデルを生成中...")
    X, y = make_classification(
        n_samples=100,
        n_features=4,
        n_informative=3,
        n_redundant=1,
        random_state=42,
    )
    model = RandomForestClassifier(n_estimators=10, random_state=42)
    model.fit(X, y)

    joblib.dump(model, model_path)
    size_kb = model_path.stat().st_size / 1024
    print(f"  モデル保存完了: {model_path} ({size_kb:.1f} KB)")


def create_model_tarball(output_dir: Path) -> Path:
    """model.tar.gz を作成する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = output_dir / "model.tar.gz"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # model.joblib を作成
        model_path = tmpdir_path / "model.joblib"
        create_dummy_model(model_path)

        # code/inference.py を作成
        code_dir = tmpdir_path / "code"
        code_dir.mkdir()
        inference_path = code_dir / "inference.py"
        inference_path.write_text(INFERENCE_PY)
        print(f"  inference.py 作成完了: {inference_path}")

        # tar.gz にパッケージング
        print(f"  model.tar.gz を作成中...")
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(model_path, arcname="model.joblib")
            tar.add(inference_path, arcname="code/inference.py")

    size_kb = tarball_path.stat().st_size / 1024
    print(f"\n✅ model.tar.gz 作成完了: {tarball_path} ({size_kb:.1f} KB)")
    print(f"\n構造:")
    print(f"  model.tar.gz")
    print(f"  ├── model.joblib")
    print(f"  └── code/")
    print(f"      └── inference.py")
    return tarball_path


def upload_to_s3(tarball_path: Path, s3_uri: str) -> None:
    """model.tar.gz を S3 にアップロードする。"""
    if not s3_uri.endswith("/"):
        s3_uri += "/"
    s3_dest = f"{s3_uri}model.tar.gz"

    print(f"\n📤 S3 にアップロード中: {s3_dest}")
    result = subprocess.run(
        ["aws", "s3", "cp", str(tarball_path), s3_dest],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: S3 アップロード失敗\n{result.stderr}")
        sys.exit(1)
    print(f"✅ アップロード完了: {s3_dest}")


def main():
    parser = argparse.ArgumentParser(
        description="SageMaker Serverless Inference テスト用モデルアーティファクト作成"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./test-data",
        help="model.tar.gz の出力ディレクトリ (default: ./test-data)",
    )
    parser.add_argument(
        "--upload",
        type=str,
        default=None,
        help="S3 URI にアップロードする (例: s3://bucket/prefix/)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SageMaker テスト用モデルアーティファクト作成")
    print("=" * 60)
    print()

    output_dir = Path(args.output_dir)
    tarball_path = create_model_tarball(output_dir)

    if args.upload:
        upload_to_s3(tarball_path, args.upload)

    print("\n使用例:")
    print(f"  # S3 にアップロード")
    print(f"  aws s3 cp {tarball_path} s3://your-bucket/models/")
    print(f"\n  # SageMaker Model 作成時に ModelDataUrl として指定")
    print(f"  ModelDataUrl: s3://your-bucket/models/model.tar.gz")


if __name__ == "__main__":
    main()
