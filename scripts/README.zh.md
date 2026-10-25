# 开发者维护脚本 (`scripts/`)

- 本目录存放面向开发与维护流程的辅助脚本（如文档检查、模型权重上传与下载等）。
- 下载预训练模型权重：`python scripts/download_models.py --help`
- 上传预训练模型权重：`python scripts/upload_models.py --help`
- 检查全仓 Google-style 英文 docstring 规范：`python scripts/check_docstrings.py`
- 面向终端用户的命令行子命令位于 [`src/sr_harness/cli/`](../src/sr_harness/cli/)。
