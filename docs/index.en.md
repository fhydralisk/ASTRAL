# SRHarness

**SRHarness** is an interactive runtime and workbench for **agentic symbolic regression**.

Instead of searching blindly over expression trees, language-model agents in SRHarness work like researchers: they inspect data distributions, analyze relationships between variables, propose mathematical hypotheses, fit constants, and refine candidate formulas across multi-turn search trajectories. Every reasoning step, tool execution, token cost, and evaluated formula is recorded as an auditable run log.

[Open the live WebUI](http://sim1.fiblab.tech:30000/){ .md-button .md-button--primary }
[View source](https://github.com/yuzhTHU/SRHarness){ .md-button }

## Documentation Guide

- **[Install](install.md)**: Set up Python, install optional packages, configure model provider API keys, or launch with Docker.
- **[Quick Start](quick-start.md)**: Recover your first equation from synthetic data or launch the interactive browser workbench.
- **[SRHarness CLI](sr-harness.md)**: Reference for the `run`, `synthetic`, `tool`, and `benchmark` commands, runtime flags, and output files.
- **[SRHarness Agent Workflow](agent.md)**: See how `SRAgent` coordinates models and tools, structures `R-C-L-K` search trees, and runs each iteration.
- **[SRHarness Core Abstractions](core-abstractions.md)**: Learn how to extend SRHarness with custom tools (`BaseTool`) and tool-call parsers (`BaseParser`).
- **[Structured Data and `context.data`](context-data.md)**: Storage format for variables, coordinate axes, graphs, and hypergraphs.
- **[Formula Evaluation and Custom Evaluators](evaluator.md)**: Understand data splitting, parameter fitting, built-in Evaluators, and how to write custom evaluation logic (such as ODE trajectory rollouts).
- **[SRHarness WebUI](web-ui.md)**: Walk through the browser workflow from data preparation and task setup to interactive symbolic regression.
- **[SRHarness Engine](engine.md)**: Learn the expression syntax, parameter declarations, and indexed notation for graphs, hypergraphs, and time delays.
- **[API Reference](https://yuzhthu.github.io/SRHarness/reference/)**: Look up public Python classes, functions, and type signatures.

## Project Links

- [English README](https://github.com/yuzhTHU/SRHarness/blob/master/README.md)
- [Chinese README](https://github.com/yuzhTHU/SRHarness/blob/master/README.zh.md)
- [GitHub Repository](https://github.com/yuzhTHU/SRHarness)
- [Live WebUI](http://sim1.fiblab.tech:30000/)
