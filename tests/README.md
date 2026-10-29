# 测试指南 (`tests/`)

> 符号引擎的可执行行为示例另见 [`tests/behavior/README.zh.md`](behavior/README.zh.md)，完整项目文档见 [`docs/index.md`](../docs/index.md)。

## 1. 运行测试命令

```bash
# 默认：仅运行快速单元测试（自动排除 slow 和 paid）
./venv/bin/python -m pytest tests/ -v

# 运行全部测试（包含慢速集成测试与付费 API 测试）
./venv/bin/python -m pytest tests/ -v -m ""

# 仅运行慢速/集成测试
./venv/bin/python -m pytest tests/ -v -m slow

# 仅运行需要真实 LLM API 额度的付费测试
./venv/bin/python -m pytest tests/ -v -m paid
```

## 2. 浏览器端前端回归测试（离线）

安装 Node.js 的 `playwright` 包及 Chromium 浏览器后，可在仓库根目录运行前端流式渲染与交互回归测试：

```bash
cd web
npm ci
npx playwright install chromium
npm run test:e2e
```

- 浏览器测试启动真实 Next.js 后端和模拟 Harness，验证登录、上传、科研工作流、暂停继续、会话切换、刷新、主题、语言及导出归档，不调用付费模型。
- Python HTTP、本地服务、幂等、并发与科研工作流测试位于 `tests/service/`；旧 Python WebUI 测试保留在 `tests/legacy_web/`，不再收集。
- Windows 下需在 WSL2 的原生 Linux 文件系统或 Docker 中验证 Landlock/openat2，具体命令见 `deploy/decoupled/README.md`。

## 3. 测试分类与 Pytest 标记

测试套件通过 `pyproject.toml` 中的 pytest marker 分为三类：

| 标记 | 适用范围 | 默认是否执行 |
|---|---|:---:|
| （无标记） | 快速单元测试：纯本地逻辑，不依赖外部网络或真实 API | **是** |
| `@pytest.mark.slow` | 慢速/集成测试：涉及较重的本地计算、子进程或端到端流程，但不产生 API 费用 | 否 |
| `@pytest.mark.paid` | 付费 API 测试：需要连接真实大模型服务商并消耗 Token 额度 | 否 |

`pyproject.toml` 默认配置了 `addopts = "--quiet -m 'not slow and not paid'"`，因此日常执行 `pytest` 时会自动跳过 `slow` 和 `paid` 测试。

```python
# 1. 快速单元测试 —— 无需添加标记
def test_parse_single_action():
    parser = TextParser(tool_list=None)
    actions = parser.parse_response("Action: foo(x=1)")
    assert len(actions) == 1


# 2. 慢速或端到端集成测试
@pytest.mark.slow
def test_format_then_parse_roundtrip():
    ...


# 3. 调用真实大模型接口的付费测试
@pytest.mark.paid
def test_llm_generates_parseable_action():
    ...
```

## 4. 测试编写规范

1. **优先使用函数式测试**：除需要共享大量复杂初始化状态的场景外，优先编写独立的 `test_*` 函数配合 `@pytest.fixture` 和 `@pytest.mark.parametrize`，保持测试简明直观：

```python
import numpy as np
import pytest
from sr_harness.core import AgentContext
from sr_harness.tools.statistics_analysis import StatisticsTool


@pytest.fixture
def sample_context():
    data = {"x1": np.array([1.0, 2.0, 3.0]), "y": np.array([2.0, 4.0, 6.0])}
    return AgentContext(data=data, target="y")


def test_execute_analyzes_selected_variables(sample_context):
    tool = StatisticsTool(context=sample_context)
    result = tool.execute(variables=["x1"])
    assert "x1" in result["statistics"]
```

2. **文件命名与目录对应**：测试文件统一命名为 `test_<模块名>.py`，并放在与 `src/` 对应的子目录中：

```text
tests/
├── conftest.py          # pytest 全局固件与环境配置
├── behavior/            # sr_harness_engine 行为规范测试
├── core/                # AgentContext、context.data 等核心数据结构测试
├── tools/               # 内置科学工具与自定义 Skill/Tool 测试
├── parser/              # 工具调用解析器测试
├── api/                 # 模型 API 客户端测试
├── cli/                 # 命令行入口测试
├── service/             # Harness 应用服务、HTTP 契约与科研流程
├── legacy_web/          # 旧 Python WebUI 测试（仅参考，不再收集）
└── deploy/              # 部署与发布脚本测试
```

3. **隔离全局状态**：
   - 无标记单元测试必须能在无外网、无 API Key 的环境下稳定通过。
   - 若测试中需要向 `BaseTool` 动态注册临时工具，请使用带唯一前缀的名称（如 `unit_sample_tool`）并在测试结束后还原注册表，避免污染其他测试。
   - `@pytest.mark.paid` 测试在缺少对应 API Key 或遇到网络异常时应调用 `pytest.skip()` 平稳跳过。
