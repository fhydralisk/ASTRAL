# SRHarness：面向智能体符号回归的研究框架与运行时

[English](README.md) | [简体中文](README.zh.md)

[![GitHub](https://img.shields.io/github/stars/yuzhTHU/SRHarness?style=flat&logo=github&label=GitHub)](https://github.com/yuzhTHU/SRHarness)
[![PyPI](https://img.shields.io/pypi/v/sr-harness?logo=pypi&logoColor=white)](https://pypi.org/project/sr-harness/)
[![Docker](https://img.shields.io/docker/v/yumeoww/sr-harness?sort=semver&logo=docker&logoColor=white&label=Docker)](https://hub.docker.com/r/yumeoww/sr-harness)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-4e968b?logo=materialformkdocs&logoColor=white)](https://yuzhthu.github.io/SRHarness/)
[![Live WebUI](https://img.shields.io/badge/WebUI-live-4e968b?logo=googlechrome&logoColor=white)](http://sim1.fiblab.tech:30000/)
[![Hugging Face WebUI](https://img.shields.io/badge/WebUI-Hugging%20Face-ffd21e?logo=huggingface&logoColor=black)](https://yumeow-srharness.hf.space/)
[![arXiv](https://img.shields.io/badge/arXiv-2609.35501-b31b1b?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2609.35501)
[![Documentation build](https://github.com/yuzhTHU/SRHarness/actions/workflows/docs.yml/badge.svg?branch=dev)](https://github.com/yuzhTHU/SRHarness/actions/workflows/docs.yml)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?logo=python&logoColor=white)](https://pypi.org/project/sr-harness/)
[![License](https://img.shields.io/github/license/yuzhTHU/SRHarness)](LICENSE)

SRHarness 是一个面向**智能体符号回归（Agentic Symbolic Regression）**的科研运行时与交互式工作台。它不再依赖盲目的随机表达式搜索或单次模型猜测，而是为大语言模型配备一套受控的科学计算工具——让 Agent 能够清洗与整理数据、检验变量关系、拟合待定参数、诊断残差，并在多轮探索轨迹中逐步打磨出简洁、可解释的数学方程。同时，内置的网页工作台支持多会话持久化、数据可视化探索以及通过自定义 `Evaluator` 扩展领域专属的公式评测逻辑。

## 核心特性

- **可组合的科学工具集：** 统计诊断、函数拟合、外部符号搜索（PySR、SINDy）、安全沙箱代码执行与公式评估共用统一的 `BaseTool` 接口。
- **持久化的全局搜索状态：** 自动记录每轮评估过的候选公式、误差指标、残差画像与搜索树节点，跨分支实时维护 Top-k 榜单与帕累托前沿（Pareto Front）。
- **结构化的 `R-C-L-K` 搜索树：** 统一调度外层重启（`R`）、并行对话分支（`C`）、单分支迭代深度（`L`）与单步多响应采样（`K`），兼顾广度探索与深度改进。
- **全流程交互式网页工作台：** 将“数据准备 → 任务与评估器配置 → 符号回归搜索”串联为可视化工作流，支持中途暂停、注入人工指导与断点恢复。
- **高表达力的底层符号引擎：** `sr_harness_engine` 原生支持普通标量公式、命名与按类别分组参数，以及带显式下标的有向图、三元超图和时延表达式。

## 实验结果

我们在[论文](https://arxiv.org/abs/2609.35501)中使用相同的底层大语言模型，在 **LLM-SRBench** 基准上对 SRHarness 进行了系统评测。其中 **LSR-Transform** 考察经过代数变换的科学方程恢复能力，**LSR-Transform-Anon** 则进一步抹去所有科学背景描述与变量名称语义，测试算法能否仅凭纯数值规律还原真实公式。下表展示了各方法的符号准确率（Symbolic Accuracy, SA）：

| 方法 / 基础模型 | LSR-Transform | LSR-Transform-Anon |
|---|---:|---:|
| SRHarness + DeepSeek-v4-flash-0731 | **93.69%** | **72.97%** |
| SR-Scientist + DeepSeek-v4-flash-0731 | 62.16% | 39.64% |
| Codex + DeepSeek-v4-flash-0731 | — | 20.72% |

在使用同一个 `DeepSeek-v4-flash-0731` 模型时，SRHarness 在两项基准上的符号恢复率均比 SR-Scientist 高出 31 个百分点以上；即便在完全隐去物理背景与变量名的匿名基准上，依然保持了 72.97% 的恢复率，并大幅领先通用编程智能体 Codex。这表明：将大语言模型与科学的分析/拟合工具、持久化的候选状态以及 `R-C-L-K` 搜索轨迹管理相结合，能够显著提升符号发现的可靠性。完整的评测设置、域外数值泛化结果、开销分析与消融实验请参阅论文。

## 安装

SRHarness 需要 Python 3.12 或更高版本：

```bash
pip install sr-harness
```

模型 API Key 配置、可选依赖项（`tools`、`nn`、`dev`）、Docker 启动方式及源码开发模式安装，请参阅[安装指南](https://yuzhthu.github.io/SRHarness/install/)。

### Hugging Face Spaces 在线体验与部署

你可以直接访问托管在 Hugging Face 上的在线工作台：<https://yumeow-srharness.hf.space/>。当主分支发布新版本时，自动化工作流会同步更新该实例、PyPI 与 Docker Hub。

如需在自己的 Hugging Face 账号下部署 Docker Space，请使用仓库中的 [Space README 模板](deploy/huggingface/README.space.md)，并参阅 [Hugging Face 部署指南](deploy/huggingface/README.md) 了解密钥配置、数据持久化与安全建议。

## 快速上手

### 1. 用命令行还原已知方程：`sr-harness synthetic`

配置好 `OPENROUTER_API_KEY` 后，运行 `sr-harness synthetic` 即可根据给定方程生成合成数据，并测试 `SRAgent` 能否从数据中反推出原方程：

```bash
sr-harness synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --x-low -2 \
  --x-high 2 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start \
  -R 1 -C 1 -L 10 -K 1
```

如果使用其他模型服务商（如 DeepSeek、OpenAI、Gemini、SiliconFlow 等），请设置相应的 API Key 环境变量，并修改 `--llm-provider` 与 `--llm-model`。

### 2. 启动交互式网页工作台：`sr-harness run`

运行 `sr-harness run` 启动本地 WebUI 服务，在浏览器中完成数据整理、任务与 Evaluator 配置、实时搜索树观察以及人机协同探索：

```bash
sr-harness run \
  --host 127.0.0.1 \
  --port 8000 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

启动后在浏览器打开 <http://127.0.0.1:8000/>。对话列表与各对话的工作区文件保存在 `./workspaces`，会话快照与搜索运行记录保存在 `./logs/webui`。你也可以直接访问在线实例：<http://sim1.fiblab.tech:30000/> 或 <https://yumeow-srharness.hf.space/>。

## 文档导航

- [项目概览](https://yuzhthu.github.io/SRHarness/)
- [快速上手](https://yuzhthu.github.io/SRHarness/quick-start/)
- [安装与模型服务配置](https://yuzhthu.github.io/SRHarness/install/)
- [命令行参考（`run`、`synthetic`、`tool`、`benchmark`）](https://yuzhthu.github.io/SRHarness/sr-harness/)
- [SRHarness 智能体工作流](https://yuzhthu.github.io/SRHarness/agent/)
- [核心抽象（`BaseTool` 与 `BaseParser`）](https://yuzhthu.github.io/SRHarness/core-abstractions/)
- [结构化数据与 `context.data`](https://yuzhthu.github.io/SRHarness/context-data/)
- [公式评估与自定义 Evaluator](https://yuzhthu.github.io/SRHarness/evaluator/)
- [SRHarness 网页工作台指南](https://yuzhthu.github.io/SRHarness/web-ui/)
- [SRHarness 符号引擎](https://yuzhthu.github.io/SRHarness/engine/)
- [API Reference](https://yuzhthu.github.io/SRHarness/reference/)

## 论文引用

```bibtex
@article{yu2026srharness,
  title   = {SRHarness: A Harness for Agentic Symbolic Regression},
  author  = {Yu, Zihan and Zhou, Shixuan and Huang, Hao and Ding, Jingtao and Li, Yong},
  journal = {arXiv preprint arXiv:2609.35501},
  year    = {2026}
}
```

## 开源许可

SRHarness 基于 [MIT License](LICENSE) 开源。
