> Web deployment now uses separate Next.js and Harness services. See [deployment](../deploy/decoupled/README.md). Provider environment variables below apply to standalone scientific CLI usage; Web model credentials are encrypted in the Next.js database.

# 安装指南

## 环境要求

- **Python**：3.12 或更高版本
- **操作系统**：Linux、macOS 或具备等价 Python 环境的系统
- **模型服务**：至少准备一个受支持大模型服务商（如 OpenRouter、DeepSeek、OpenAI、Gemini、SiliconFlow 等）的 API Key

!!! note "关于代码执行沙箱（Landlock ABI 3+）"
    SRHarness 中的代码执行工具（`code_executor`、`evaluate_code`、`workspace_code_executor`）以及自定义 Tool / Evaluator 采用 Linux 内核自带的 **Landlock** 与 **seccomp** 实现系统级安全隔离。

    - Landlock 是 Linux 内核内置的安全模块，无需通过 `pip` 或 `apt` 单独安装。
    - SRHarness 要求内核支持 **Landlock ABI 3 或更高版本**（通常对应 **Linux 6.2+** 内核），以便严格限制文件截断与越权写入。
    - 如果当前系统的内核不支持或未启用 Landlock，你仍然可以使用纯公式解析、内置拟合等不涉及任意代码执行的功能；但调用上述代码沙箱工具时会直接抛出 `SandboxUnavailableError`，而不会退化为仅靠 Python 语法检查的弱隔离。

    你可以通过以下命令检查当前内核支持的 Landlock ABI 版本：

    ```bash
    python -c "from sr_harness.runtime.landlock import landlock_abi; print(landlock_abi())"
    ```

## 从 PyPI 安装（推荐）

如果只需要运行 SRHarness 或使用网页工作台，可直接通过 `pip` 安装：

```bash
pip install sr-harness
```

安装完成后，运行以下命令验证命令行入口与核心模块是否正常：

```bash
sr-harness --help
python -c "import sr_harness, sr_harness_engine; print('SRHarness is ready')"
```

## 使用 Docker 启动

如果你不想在宿主机配置 Python 环境，可以直接使用发布在 [Docker Hub](https://hub.docker.com/r/yumeoww/sr-harness) 上的官方镜像。该镜像已预装 WebUI 和常用研究工具（`tools` 扩展）。

首先在当前目录创建一个 `.env` 文件并填入模型 API Key，然后执行：

```bash
docker volume create sr-harness-data
docker pull yumeoww/sr-harness:latest
docker run --detach \
  --name sr-harness \
  --restart unless-stopped \
  --env-file .env \
  --publish 127.0.0.1:8000:8000 \
  --volume sr-harness-data:/data \
  yumeoww/sr-harness:latest
```

启动后在浏览器访问 `http://127.0.0.1:8000/` 即可。其中 `sr-harness-data` 数据卷会持久保存对话列表、各对话的工作区文件及运行记录，删除或升级容器不会丢失数据。

日常查看日志与启停容器的常用命令：

```bash
docker logs --follow --tail 100 sr-harness
docker stop sr-harness
docker start sr-harness
```

如果需要从局域网或外部机器访问，可将端口映射改为 `--publish 8000:8000` 并放行相应防火墙端口。请注意：SRHarness 本身不包含账号登录或网关鉴权功能，将服务暴露到公网前请务必前置反向代理、配置 HTTPS (TLS) 与访问控制。

!!! warning "容器部署安全提示"
    Docker 能隔离宿主机文件与进程，但传入同一容器的环境变量仍可能被容器内执行的代码读取。请勿将包含敏感文件的宿主机目录直接挂载到 `/data`。若要面向不可信用户开放公网服务，建议将真实 API Key 托管在独立的转发网关中，并限制容器的出站网络。

## 从源码安装（开发模式）

如果你需要修改 SRHarness 源码、运行测试套件或本地构建文档，建议使用可编辑模式安装：

```bash
git clone https://github.com/yuzhTHU/SRHarness.git SRHarness
cd SRHarness
conda create -p ./venv python=3.12 -y
conda activate ./venv
python -m pip install --upgrade pip
pip install -e '.[all]'
```

## 可选依赖包（Extras）

为了避免默认安装体积过大，SRHarness 将部分重量级依赖拆分成了按需安装的扩展项：

| 扩展名 | 包含内容 | 安装命令 |
|---|---|---|
| `tools` | PySR、PySINDy、PDF 解析等符号回归与科研辅助工具 | `pip install 'sr-harness[tools]'` |
| `nn` | PyTorch 与 PyTorch Geometric（图神经网络相关工具） | `pip install 'sr-harness[nn]'` |
| `dev` | pytest、MkDocs、Material 主题、mkdocstrings 等测试与文档工具 | `pip install 'sr-harness[dev]'` |
| `all` | 安装上述全部可选依赖 | `pip install 'sr-harness[all]'` |

例如，同时安装研究工具和开发依赖：

```bash
pip install 'sr-harness[tools,dev]'
```

若在源码目录中进行本地开发，只需把命令替换为 `pip install -e '.[tools,dev]'`。

!!! note
    PySR（依赖 Julia 环境）和 PyTorch 的安装耗时较长。如果只是初次体验 SRHarness，先安装基础包即可，后续用到对应工具时再补充安装。

## 配置模型服务 API Key

你可以在运行目录下创建 `.env` 文件，或直接在终端环境变量中导出所用服务商的 API Key。以 OpenRouter 为例：

```dotenv
OPENROUTER_API_KEY="sk-or-v1-..."
```

如果是从源码安装，也可以直接复制模板文件：`test -f .env || cp .env.sample .env`，再填入你的密钥。

常用模型服务商的环境变量如下：

| 服务商 (Provider) | 环境变量名 | 获取 API Key |
|---|---|---|
| OpenRouter | `OPENROUTER_API_KEY` | [OpenRouter Keys](https://openrouter.ai/settings/keys) |
| DeepSeek | `DEEPSEEK_API_KEY` | [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) |
| Gemini | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| SiliconFlow | `SILICONFLOW_API_KEY` | [SiliconFlow 密钥管理](https://cloud.siliconflow.cn/account/ak) |
| OpenAI / Azure OpenAI | `OPENAI_API_KEY`、`OPENAI_ENDPOINT`、`OPENAI_API_VERSION` | [OpenAI Platform](https://platform.openai.com/api-keys) / [Azure Portal](https://portal.azure.com/) |

除了通过环境变量配置，你也可以直接在 [SRHarness 网页工作台](web-ui.md) 的设置面板中填写 API Key。在网页中填写的密钥会单独保存在当前对话私有的 `sessions/{CONVERSATION_ID}/.env` 中，既不会暴露给其他对话，也不会被 Agent 的工作区工具读取。

## 配置网络代理

如果访问外部模型服务需要通过代理，可以在终端设置 `HTTP_PROXY` 和 `HTTPS_PROXY`：

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

同样地，你也可以在 [SRHarness 网页工作台](web-ui.md) 的 Agent 设置面板中直接填写代理地址，配置会自动保存在当前对话私有的 `.env` 文件中。

## 启动与验证

运行以下命令启动交互式网页工作台：

```bash
sr-harness run --save-path ./sr-harness --host 127.0.0.1 --port 8000
```

随后在浏览器中打开 `http://127.0.0.1:8000/` 即可开始使用。

## 本地预览与构建文档

如果你想在本地预览或修改本项目文档：

```bash
git clone https://github.com/yuzhTHU/SRHarness.git SRHarness
cd SRHarness
pip install -e '.[dev]'
mkdocs serve
```

浏览器打开 `http://127.0.0.1:8001/` 即可实时预览。提交或发布前建议运行严格模式检查链接与格式：

```bash
mkdocs build --strict
```
