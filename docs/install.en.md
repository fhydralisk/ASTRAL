> Web deployment now uses separate Next.js and Harness services. See [deployment](../deploy/decoupled/README.md). Provider environment variables below apply to standalone scientific CLI usage; Web model credentials are encrypted in the Next.js database.

# Install

## Requirements

- **Python**: 3.12 or newer
- **Operating System**: Linux, macOS, or an equivalent Python environment
- **Model Provider**: An API key for at least one supported LLM provider (such as OpenRouter, DeepSeek, OpenAI, Gemini, or SiliconFlow)

!!! note "Kernel Sandbox Requirement (Landlock ABI 3+)"
    Code-execution tools (`code_executor`, `evaluate_code`, `workspace_code_executor`) as well as custom Tools and custom Evaluators rely on Linux **Landlock** and **seccomp** for kernel-level isolation.

    - Landlock is a built-in Linux Security Module in the kernel, not a package installed via `pip` or `apt`.
    - SRHarness requires **Landlock ABI 3 or newer** (typically **Linux 6.2+**) so the sandbox can block unauthorized file truncation and writes.
    - On kernels or platforms without Landlock support, you can still use all features that do not execute arbitrary Python code, but calling sandboxed code-execution entry points will raise `SandboxUnavailableError` rather than falling back to weak AST-only checks.

    You can check the Landlock ABI version supported by your current kernel with:

    ```bash
    python -c "from sr_harness.runtime.landlock import landlock_abi; print(landlock_abi())"
    ```

## Install from PyPI (Recommended)

To run SRHarness or launch the interactive WebUI workbench, install the package from PyPI:

```bash
pip install sr-harness
```

Verify that the CLI and core packages work properly:

```bash
sr-harness --help
python -c "import sr_harness, sr_harness_engine; print('SRHarness is ready')"
```

## Run with Docker

If you prefer not to manage a local Python environment, use the official image on [Docker Hub](https://hub.docker.com/r/yumeoww/sr-harness), which comes pre-installed with the WebUI and the `tools` extras.

Create a `.env` file in your current directory containing your model provider's API key, then run:

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

Open `http://127.0.0.1:8000/` in your browser. The `sr-harness-data` Docker volume stores your conversation list, workspaces, and run logs persistently across container restarts or upgrades.

Useful commands for viewing logs and managing the container:

```bash
docker logs --follow --tail 100 sr-harness
docker stop sr-harness
docker start sr-harness
```

To allow access from other machines, change the port flag to `--publish 8000:8000` and open the port in your firewall. Note that SRHarness does not include built-in user authentication; always place it behind a reverse proxy with TLS and access control before exposing it to an untrusted network.

!!! warning "Container Security Note"
    While Docker isolates host files and processes, environment variables passed directly into the container may still be readable by code running inside it. Never mount sensitive host directories at `/data`. For public multi-user deployments, keep real API keys in a separate proxy gateway and restrict container outbound traffic.

## Install from Source (Development)

If you want to modify SRHarness, run the test suite, or build the documentation locally, install it in editable mode:

```bash
git clone https://github.com/yuzhTHU/SRHarness.git SRHarness
cd SRHarness
conda create -p ./venv python=3.12 -y
conda activate ./venv
python -m pip install --upgrade pip
pip install -e '.[all]'
```

## Optional Dependencies (Extras)

Heavyweight or specialized dependencies are grouped into optional extras so the base installation stays fast and lightweight:

| Extra | Included Packages | Install Command |
|---|---|---|
| `tools` | PySR, PySINDy, PDF reading, and scientific discovery tools | `pip install 'sr-harness[tools]'` |
| `nn` | PyTorch and PyTorch Geometric | `pip install 'sr-harness[nn]'` |
| `dev` | pytest, MkDocs, Material, mkdocstrings, and developer utilities | `pip install 'sr-harness[dev]'` |
| `all` | All optional extras above | `pip install 'sr-harness[all]'` |

For example, to install both research tools and development utilities:

```bash
pip install 'sr-harness[tools,dev]'
```

When working from a source checkout, use `pip install -e '.[tools,dev]'`.

!!! note
    Packages like PySR and PyTorch take longer to install and may have platform-specific requirements. You can start with the base package and install extras later as needed.

## Configure Model Providers

Create a `.env` file in your working directory or export the environment variable for your model provider in your shell. For example, with OpenRouter:

```dotenv
OPENROUTER_API_KEY="sk-or-v1-..."
```

In a source checkout, you can also copy the sample file via `test -f .env || cp .env.sample .env` and fill in your keys.

Common provider environment variables:

| Provider | Environment Variables | Get an API Key |
|---|---|---|
| OpenRouter | `OPENROUTER_API_KEY` | [OpenRouter Keys](https://openrouter.ai/settings/keys) |
| DeepSeek | `DEEPSEEK_API_KEY` | [DeepSeek Platform](https://platform.deepseek.com/api_keys) |
| Gemini | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| SiliconFlow | `SILICONFLOW_API_KEY` | [SiliconFlow API Keys](https://cloud.siliconflow.cn/account/ak) |
| OpenAI / Azure OpenAI | `OPENAI_API_KEY`, `OPENAI_ENDPOINT`, `OPENAI_API_VERSION` | [OpenAI API Keys](https://platform.openai.com/api-keys) / [Azure Portal](https://portal.azure.com/) |

You can also enter API keys directly in the [WebUI](web-ui.md) settings panel. Keys saved through the WebUI are stored in each conversation's private `sessions/{CONVERSATION_ID}/.env` and are isolated from Agent workspace tools and other conversations.

## Proxy Configuration

If you need an HTTP/HTTPS proxy to reach model APIs, export `HTTP_PROXY` and `HTTPS_PROXY`:

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
```

You can also set a proxy URL per conversation inside the [WebUI](web-ui.md) Agent settings panel.

## Verify and Launch

Start the interactive workbench locally:

```bash
sr-harness run --save-path ./sr-harness --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/` in your browser.

## Build the Documentation

To preview or build this documentation site locally:

```bash
git clone https://github.com/yuzhTHU/SRHarness.git SRHarness
cd SRHarness
pip install -e '.[dev]'
mkdocs serve
```

Open `http://127.0.0.1:8001/` in your browser. Before publishing changes, run a strict build check:

```bash
mkdocs build --strict
```
