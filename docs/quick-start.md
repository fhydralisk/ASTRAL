# 快速上手

在开始之前，请确认已完成 [安装与模型 API Key 配置](install.md)。

## 1. 用命令行还原一个已知公式

`sr-harness synthetic` 是体验 SRHarness 最快的方式：它会先按你给定的数学公式生成一批合成数据，然后让 Agent 仅凭这些数据去反推背后的公式。

下面我们生成包含 `x1`、`x2`、`y` 三列的数据，其中因变量 `y` 的真实生成规律为：

$$
y = 1 + x_1^2 + 2x_1x_2
$$

!!! tip
    运行前请先配置与 `--llm-provider` 对应的环境变量。以下示例使用 OpenRouter（需设置 `OPENROUTER_API_KEY`）；如果你使用 DeepSeek 或其他服务商，请同步修改 `--llm-provider` 和 `--llm-model`。

执行以下命令，以一个较小的搜索预算启动 Agent：

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

其中 `-R`、`-C`、`-L`、`-K` 四个参数共同控制搜索规模：

| 参数 | 含义 |
|---|---|
| `-R` | **重启次数 (Restart)**：带着历史最优公式重新开启一轮搜索的次数 |
| `-C` | **并行分支数 (Conversation)**：每次重启同时探索的独立对话分支数 |
| `-L` | **最大迭代步数 (Refinement Depth)**：每条对话分支最多允许交互的轮数 |
| `-K` | **单步采样数 (Local Sample)**：每一轮向模型同时采样生成的回复数 |

运行结束后，所有过程数据都会保存在 `--save-path`（本例为 `./logs/quick-start`）下：

| 文件名 | 记录内容 |
|---|---|
| `run.json` | 本次运行的基础信息、命令行参数与 Agent 配置 |
| `nodes.jsonl` | 搜索树中每个 `(R, C, L, K)` 对话节点及父子继承关系 |
| `result.json` | 探索过的所有候选公式、帕累托前沿（Pareto Front）及最终最优公式 |
| `response.jsonl` | 模型原始返回内容、Token 消耗与费用明细 |
| `tool_calls.jsonl` | 每次工具调用的输入参数与返回结果 |

一次典型的终端运行日志如下：

```text {.srh-log}
$ sr-harness synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --x-low -2 \
  --x-high 2 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start \
  -R 1 -C 1 -L 10 -K 1

[20261009_synthetic_173140_SIM1|synthetic|N|Oct09 17:31:40|0:00:00.000742] Args: Namespace(command='synthetic', name='synthetic', exp_name='20261009_synthetic_173140_SIM1', save_dir='./logs/synthetic', equation='y = 1 + x1 ** 2 + 2 * x1 * x2', problem_description=None, features=None, n_samples=200, seed=42, x_low=-2.0, x_high=2.0, noise_std_ratio=0.0, llm_provider='openrouter', llm_model='deepseek/deepseek-v4-flash-0731', strong_llm_provider=None, strong_llm_model=None, tools=None, ban_tools=[], local_sample_size=1, max_refinement_depth=10, global_width=1, max_restart_loop=1, restart_top_k=1, llm_max_tokens=4096, tool_parser='openai', save_path='logs/quick-start', verbose=False, debug=False, max_workers=0, validation_fraction=0.2, split_by='random', split_ood_variable=None, split_random_state=42, force_initial_diagnostics=True, auto_routing=True, invocation='sr-harness synthetic')
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.014988] Initialized SRAgent
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.019464] Start Restart Loop (R=1/1)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.020326] (R=1/1) × Global Branch (C=1/1)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.020527] (R=1/1) × (C=1/1) × Refinement Step (L=1/10)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.040948] Built prompt with 4 messages.
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:40|0:00:00.153329] Model route: tier=base, backend=openrouter/deepseek/deepseek-v4-flash-0731, score=0, reason=no distinct strong backend configured
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.662623] (R=1/1) × (C=1/1) × (L=1/10) × Local Sample (K=1/1)
        LLM response content: (empty)
        LLM tool calls: (3 tool calls)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.753144] Selected LLM branch: 1/1
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.765089] Progress=(R=1/1) × (C=1/1) × (L=1/10) × (K=1) | Best=1 + 2 * (x1 * x2) + 1 * x1 ** 2 (validation MSE=2.3692e-30) | Tool Calls=statistics_analysis: 1 (0 new), relationship_analysis: 2 (1 new), read_skill: 1 (0 new), polynomial_fit: 1 (1 new), call_sindy: 1 (1 new) | Speed=0 s/iter | Time Usage=14.7 s (request_llm=14.5 s/iter[98%]; prepare_model_messages=133 ms/iter[1%]; execute_tool_calls=81.6 ms/iter[1%]; record_search_iteration=6.01 ms/iter[0%]; create_initial_buffer=859 μs/iter[0%]; update_conversation=478 μs/iter[0%]; init_buffer=204 μs/iter[0%]; collect_candidates=50.3 μs/iter[0%]) | Token Usage=14 ktoken (prompt=890 token/s[93%]; answer=63.3 token/s[7%]) | Price Usage=1.37 m$ (total=8.05 $/day[100%])
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.765574] (R=1/1) × (C=1/1) × Refinement Step (L=2/10)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.765853] Built prompt with 9 messages.
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:31:55|0:00:14.867024] Model route: tier=base, backend=openrouter/deepseek/deepseek-v4-flash-0731, score=0, reason=no distinct strong backend configured
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:32:10|0:00:29.998812] (R=1/1) × (C=1/1) × (L=2/10) × Local Sample (K=1/1)
        LLM response content:
                The polynomial fit found the exact formula: y = 1 + 2·x1·x2 + x1² with RMSE ~1.7e-15 (machine precision). This is
                essentially exact. Let me verify and submit it.
        LLM tool calls: (2 tool calls)
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:32:10|0:00:30.046342] Selected LLM branch: 1/1
[20261009_synthetic_173140_SIM1|sr_agent|I|Oct09 17:32:10|0:00:30.054810] Progress=(R=1/1) × (C=1/1) × (L=2/10) × (K=1) | Best=1 + x1 ** 2 + 2 * x1 * x2 (validation MSE=0) | Tool Calls=statistics_analysis: 1 (0 new), relationship_analysis: 2 (0 new), read_skill: 1 (0 new), polynomial_fit: 1 (0 new), call_sindy: 1 (0 new), evaluate_formula: 1 (1 new), submit_formula: 1 (1 new) | Speed=14.7 s/iter | Time Usage=30 s (request_llm=14.8 s/iter[99%]; prepare_model_messages=117 ms/iter[1%]; execute_tool_calls=59.8 ms/iter[0%]; record_search_iteration=6.27 ms/iter[0%]; log_info=12 ms/iter[0%]; update_conversation=667 μs/iter[0%]; create_initial_buffer=859 μs/iter[0%]; init_buffer=204 μs/iter[0%]; collect_candidates=86.4 μs/iter[0%]) | Token Usage=32.5 ktoken (prompt=1.03 ktoken/s[95%]; answer=50.9 token/s[5%]) | Price Usage=2.38 m$ (total=6.85 $/day[100%])
[20261009_synthetic_173140_SIM1|sr_agent|N|Oct09 17:32:10|0:00:30.055465] Early stopping triggered. Returning best result.
[20261009_synthetic_173140_SIM1|synthetic|N|Oct09 17:32:10|0:00:30.099796]
        ==================================================
        Symbolic Regression Result
        Start Time: 2026-10-09 17:31:40
        Duration Seconds: 30.759567
        Target Formula: y = 1 + x1 ** 2 + 2 * x1 * x2
        Noise Std Ratio: 0.0
        Random Seed: 42
        Status: early_stopped
        Progress: (R=1/1) × (C=1/1) × (L=2/10) × (K=1)
        Token Usage: 32.5 ktoken
        Money Usage: 2.38 m$
        Tools Usage: 8 call (relationship_analysis=2 call[25%]; statistics_analysis=1 call[12%]; read_skill=1 call[12%]; polynomial_fit=1 call[12%]; call_sindy=1 call[12%]; evaluate_formula=1 call[12%]; submit_formula=1 call[12%])
        Llm Model: deepseek/deepseek-v4-flash-0731 @ openrouter [autorouting to deepseek/deepseek-v4-flash-0731 @ openrouter]
        Best Candidate: 0
        Times Usage: 30 s (request_llm=14.8 s/iter[99%]; prepare_model_messages=117 ms/iter[1%]; execute_tool_calls=59.8 ms/iter[0%]; log_info=10.1 ms/iter[0%]; record_search_iteration=6.27 ms/iter[0%]; update_conversation=667 μs/iter[0%]; create_initial_buffer=859 μs/iter[0%]; init_buffer=204 μs/iter[0%]; collect_candidates=86.4 μs/iter[0%])

        Pareto Front
        Balance: minimize Complexity; maximize Validation R².
        =================================================================
        #  Complexity  Validation R²  Train R²  Formula
        -----------------------------------------------------------------
        1          11              1         1  1 + x1 ** 2 + 2 * x1 * x2
        =================================================================
        ==================================================
[20261009_synthetic_173140_SIM1|synthetic|N|Oct09 17:32:10|0:00:30.101931] Result saved to logs/quick-start/result.jsonl
[20261009_synthetic_173140_SIM1|synthetic|N|Oct09 17:32:10|0:00:30.102261] Experiment completed. Re-run the script with sr-harness synthetic
```

## 2. 使用交互式网页工作台（WebUI）

对于真实的科研数据，通常需要先清洗数据、构造导数或特征，并在搜索过程中随时介入指导。这时可以使用交互式网页工作台。

运行以下命令在本机 `8000` 端口启动服务，并将工作区和运行日志分别保存在 `./workspaces` 与 `./logs/webui`：

```bash
sr-harness run \
  --host 127.0.0.1 \
  --port 8000 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

浏览器打开 `http://127.0.0.1:8000/` 后，按顶部标签依次完成三个步骤即可：

1. **数据准备**：上传原始数据（或一键生成内置样例），让数据准备 Agent 帮你清洗、计算导数或整理成标准格式。
2. **任务配置**：指定因变量与自变量、补充各变量的物理含义，并选择或定制公式评测方案（Evaluator）。
3. **符号回归**：启动公式搜索，实时查看推理时间线、搜索树与候选公式；你也可以随时暂停搜索，补充提示词或返回前两步调整变量与评测指标。

![SRHarness 符号回归工作台](assets/webui-symbolic-regression.png)

详细功能说明请参阅 [SRHarness 网页工作台](web-ui.md)。

### 挂载本地大数据集（只读）

如果本地数据集体积较大、或者不希望原始数据被 Agent 改动，可以通过 `--mount` 将本地文件或目录直接挂载到工作区：

```bash
sr-harness run \
  --workspace-dir ./workspaces \
  --mount ./datasets ./papers/model.pdf
```

挂载的文件或文件夹会以只读方式出现在每个对话的工作区中——既省去了重复拷贝占用的磁盘空间，也能防止 Agent 误改原始数据。注意：同时挂载多个路径时，它们的顶层文件或文件夹名称不能重名。

## 3. 直接体验在线工作台

如果你不想在本地安装部署，也可以直接打开我们托管的 [在线 WebUI 工作台](http://sim1.fiblab.tech:30000/)，在浏览器中直接体验完整工作流。
