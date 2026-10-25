# 内嵌第三方代码说明 (`src/sr_harness/_vendor/`)

本目录存放随 `sr_harness` 一起打包分发的内部定制版第三方源码（如 `llmsr_bench` 评测适配层）。

一般而言，常规第三方依赖应直接声明在 `pyproject.toml` 中并通过 `pip` 安装。仅当外部代码满足以下情况时，才将其内嵌至本目录：

1. 原始仓库缺少标准 Python 包结构，无法通过 `pip` 直接安装；
2. 需要针对 SRHarness 的数据流、接口或沙箱环境做定制修改。

## 导入约定

请始终通过 `sr_harness._vendor` 绝对路径导入本目录下的模块：

```python
import sr_harness._vendor.llmsr_bench
```

不要将 `_vendor/` 子目录直接加入 `sys.path`，也不要让同一份源码同时以顶层包名和 `sr_harness._vendor.*` 两种路径被导入，以免 Python 创建重复的模块对象导致 `isinstance` 检查、注册表或缓存失效。
