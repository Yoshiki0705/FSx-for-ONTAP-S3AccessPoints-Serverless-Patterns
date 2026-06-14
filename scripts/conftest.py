# scripts/ ディレクトリは pytest の収集対象外（tests/ サブディレクトリを除く）
import os

collect_ignore_glob = []

# tests/ ディレクトリ以外の .py ファイルを無視
for f in os.listdir(os.path.dirname(__file__)):
    if f.endswith(".py") and f != "conftest.py" and f != "__init__.py":
        collect_ignore_glob.append(f)
