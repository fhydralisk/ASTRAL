# SRHarness Engine 行为测试集 (`tests/behavior/`)

本目录通过一组可读性强的行为测试展示 `sr_harness_engine` 与 `Evaluator` 的核心用法。所有测试仅调用公开 API，不依赖内部私有实现细节，可直接作为代码示例参考。

单独运行行为测试：

```bash
pytest -q tests/behavior
```

各测试文件覆盖的功能模块：

- `test_basic_expressions.py`：表达式构建、字符串解析、规范化与 LaTeX 渲染、NumPy 广播及初等函数；
- `test_parameters.py`：命名标量参数（`param`）、同名共享参数、参数拟合与按类别分组参数（`grouped_param`）；
- `test_relations.py`：全局下标归约、有向图、三元超图及 `aggr/targ/sour` 简写语法；
- `test_gather.py`：多自由下标稠密展开与边/超边级特征提取（`gather`）；
- `test_delay.py`：默认时延线性插值（`delay`）与自定义历史状态查询函数（`delay_resolver`）；
- `test_simplification.py`：纯常数子表达式折叠与自由参数计数；
- `test_language_boundaries.py`：AST 安全解析边界、未绑定参数报错与表达式树遍历；
- `test_custom_evaluator.py`：自定义 `DefaultEvaluator` / `GraphEvaluator` 扩展、沙箱加载与安全隔离。
