# 外部独立仓库目录 (`third-party/`)

本目录用于存放保持独立仓库结构的外部依赖或可选科研后端（如 `ND2`、`SR4MDL` 等），便于在本地阅读源码、调试或以可编辑模式安装。

- 若外部项目本身具备标准的 `pyproject.toml` 或 `setup.py`，建议在虚拟环境中以可编辑模式安装：
  ```bash
  pip install -e ./third-party/<project>
  ```
- 导入时请直接使用该包自身的顶层包名（或通过 `ND2_HOME`、`SR4MDL_HOME` 等环境变量指向对应目录），不要把 `third-party/` 根目录直接加入 `PYTHONPATH`，也不要使用 `import third_party.<project>`。
- 若某份第三方代码无法直接安装且必须随 `sr_harness` 发行包一起分发，请将其整理后放入 [`src/sr_harness/_vendor/`](../src/sr_harness/_vendor/)。
