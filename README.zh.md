> Architecture update: the React/Next.js app is in `web/`; run the independent Harness with `astral serve`. See [deployment and development](deploy/decoupled/README.md). The legacy `astral run` WebUI has been removed. Historical data is not migrated.

# ASTRAL

**基于 [SRHarness](https://github.com/yuzhTHU/SRHarness) 构建的人机交互天文发现平台。**

[English](README.md) | [简体中文](README.zh.md)

[![GitHub](https://img.shields.io/github/stars/yuzhTHU/ASTRAL?style=flat&logo=github&label=GitHub)](https://github.com/yuzhTHU/ASTRAL)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-173b73?logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/github/license/yuzhTHU/ASTRAL)](LICENSE)

ASTRAL 将科学数据准备、智能体符号回归、公式评估和人工指导整合到交互式研究工作台中，并在 SRHarness 的基础上逐步发展天文发现工作流。

天文数据集、领域知识和专用天文技能是后续计划扩展的能力。当前版本提供继承自 SRHarness 的科学研究流程、ASTRAL 品牌界面，以及支持浅色和深色模式的深蓝主题。

## 当前能力

- 持久化对话与工作区，支持持续开展科学探索。
- 交互式数据准备与任务配置。
- 可组合的数据分析、拟合与评估工具。
- 自定义 Evaluator、可解释的候选公式和搜索诊断。
- 搜索过程中的人工指导，以及中英文界面。

## 源码安装

需要 Python 3.12 或更高版本。目前通过源码安装，暂未配置 PyPI 和 Docker Hub 发布。

```bash
git clone git@github.com:yuzhTHU/ASTRAL.git
cd ASTRAL
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

安装包名和命令均为 `astral`。为便于持续合并上游更新，Python 导入路径沿用 `sr_harness` 和 `sr_harness_engine`。

## 启动交互式工作台

前后端位于根目录 `web/`，通过内部 HTTP 调用独立的 Harness 服务。推荐按照 [部署与开发指南](deploy/decoupled/README.md) 使用根目录 Compose 启动 Next.js、Harness 和 PostgreSQL。

本地开发时，先配置 `HARNESS_SERVICE_TOKEN` 并启动科学运行时：

```bash
astral serve --host 127.0.0.1 --port 8000 --root ./harness-data
```

另一个终端进入 `web/`，配置 `.env.local`，运行 `npm ci`、`npm run db:migrate` 和 `npm run dev`，浏览器访问 `http://localhost:3000`。Harness 的安全文件操作和沙箱执行要求 Linux。

工作台使用账号登录。默认开放注册；管理员可以切换为邀请注册或管理员创建账号。模型 Key 与 Endpoint 由 Next.js 管理，Key 在数据库中加密保存，执行时按需下发。旧 WebUI 数据不自动迁移。

配置 `OPENROUTER_API_KEY` 后，也可以运行合成数据的符号回归示例：

```bash
astral synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start
```

## 同步上游

ASTRAL 是保留 SRHarness 历史的独立仓库。`origin` 指向 ASTRAL，`upstream` 指向 SRHarness：

```bash
git remote add upstream git@github.com:yuzhTHU/SRHarness.git
git fetch upstream
git switch -c sync/srharness main
git merge upstream/master
```

解决冲突并完成验证后，将同步分支合并到 `main`。使用常规合并提交保留上游提交的祖先关系。

## 文档与致谢

继承的引擎与工作流参见 [SRHarness 文档](https://yuzhthu.github.io/SRHarness/)和仓库内的 [docs](docs/) 目录。这些文档可能仍使用上游项目名称及 `sr-harness` 命令，在本项目中请使用 `astral`。

ASTRAL 基于 [SRHarness](https://github.com/yuzhTHU/SRHarness) 开发，相关研究参见论文 [SRHarness: A Harness for Agentic Symbolic Regression](https://arxiv.org/abs/2609.35501)。上游项目的研究结果应归属于 SRHarness。

本项目采用 [MIT License](LICENSE)。
