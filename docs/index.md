# SRHarness

**SRHarness** 是一个面向智能体符号回归（Agentic Symbolic Regression）的交互式研究框架与运行时。

在传统符号回归中，算法往往只是盲目搜索数学表达式；而在 SRHarness 中，大语言模型（LLM）可以像科研人员一样调用一套受控工具——先观察数据分布与变量关系，再提出公式假设、拟合常数、评估残差，并在多轮迭代中逐步逼近既准确又可解释的数学定律。整个探索过程中的每一步推理、工具调用、模型开销和候选公式都会被完整记录下来，方便随时回溯与复现。

[打开在线 WebUI](http://sim1.fiblab.tech:30000/){ .md-button .md-button--primary }
[查看源码](https://github.com/yuzhTHU/SRHarness){ .md-button }

## 文档导览

- **[安装指南 (Install)](install.md)**：配置 Python 环境、安装可选依赖、设置模型 API Key 或使用 Docker 一键启动。
- **[快速上手 (Quick Start)](quick-start.md)**：用一条命令跑通首个公式发现任务，或在浏览器中体验交互式工作台。
- **[命令行参考 (SRHarness CLI)](sr-harness.md)**：全面了解 `run`、`synthetic`、`tool`、`benchmark` 四大子命令的运行参数与输出文件结构。
- **[智能体工作流 (Agent Workflow)](agent.md)**：了解 `SRAgent` 如何闭环驱动模型与工具、组织 `R-C-L-K` 搜索树，以及管理每轮迭代。
- **[核心抽象 (Core Abstractions)](core-abstractions.md)**：了解如何通过 `BaseTool` 与 `BaseParser` 扩展自定义工具和工具调用解析器。
- **[结构化数据与 `context.data`](context-data.md)**：查阅数据集目录规范，包括常规变量、坐标轴以及图/超图网络数据的存储格式。
- **[公式评估与自定义 Evaluator](evaluator.md)**：了解数据切分、参数拟合与指标计算流程，以及如何编写任务专属的评测逻辑（如微分方程轨迹积分）。
- **[网页工作台 (WebUI)](web-ui.md)**：通过可视化界面完成“数据准备 → 任务配置 → 符号回归”全流程。
- **[符号引擎 (SRHarness Engine)](engine.md)**：学习底层数学表达式语法、待拟合参数定义，以及图、超图和时延表达式的写法。
- **[API 参考 (API Reference)](reference/index.md)**：查询公开 Python 类、函数与方法签名。

## 相关链接

- [English README](https://github.com/yuzhTHU/SRHarness/blob/master/README.md)
- [中文 README](https://github.com/yuzhTHU/SRHarness/blob/master/README.zh.md)
- [GitHub 源码仓库](https://github.com/yuzhTHU/SRHarness)
- [在线 WebUI 体验](http://sim1.fiblab.tech:30000/)
