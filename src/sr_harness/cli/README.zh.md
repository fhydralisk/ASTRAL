# 命令行子命令模块 (`src/sr_harness/cli/`)

本目录实现 `sr-harness` 命令行工具的四个子命令入口（`run`、`synthetic`、`benchmark`、`tool`）。

每个子命令模块均遵循统一约定：

- `setup_parser(parser)`：向 `argparse.ArgumentParser` 注册该子命令的参数并返回 parser；
- `main(args)`：接收解析后的 `argparse.Namespace`，执行命令逻辑并返回整数退出码（`0` 表示成功）。

模型检查点的上传、下载及代码规范检查等开发维护脚本位于仓库根目录的 [`scripts/`](../../../scripts/) 下。

> 完整的 CLI 参数说明与使用示例请参阅 [`docs/sr-harness.md`](../../../docs/sr-harness.md)。
