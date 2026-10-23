# Deploying SRHarness on Hugging Face Spaces

SRHarness can run as a Hugging Face Docker Space using the repository's root
`Dockerfile`. The Space metadata at the top of the root `README.md` tells
Hugging Face to expose the application's existing port, `8000`.

## 1. Create the Space

Create a new Space with the **Docker** SDK. A private Space is recommended when
the deployment uses an owner-funded model API key. Then push this repository to
the Space repository:

```bash
git remote add huggingface https://huggingface.co/spaces/OWNER/SPACE_NAME
git push huggingface HEAD:main
```

The container starts the equivalent of:

```bash
sr-harness run \
  --save-path /data \
  --workspace-dir /data \
  --isolate-users \
  --host 0.0.0.0 \
  --port 8000
```

The health endpoint is `/health`.

## 2. Configure model credentials

Add provider credentials under the Space's **Settings → Secrets**. Supported
secret names include:

- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `SILICONFLOW_API_KEY`
- `GEMINI_API_KEY`

Never add API keys as repository files or public Space variables.

For a public Space, avoid installing an owner-funded key unless unrestricted
public use and its cost are intentional. SRHarness lets each browser session
configure its own provider key in the WebUI, but `--isolate-users` is
cookie-based isolation rather than authentication or abuse prevention.

## 3. Choose a storage policy

The image writes conversations, uploaded data, settings, and run artifacts to
`/data`.

- Without persistent storage, Space restarts can erase `/data`.
- To retain work, attach persistent storage or a writable Storage Bucket at
  `/data` in the Space settings.
- Persisted workspaces can contain user-uploaded data and provider keys entered
  through the WebUI. Use a private Space for sensitive work and apply an
  appropriate retention policy.

## 4. Resource expectations

CPU Basic is enough to start the WebUI and use remote LLM providers. Symbolic
regression workloads can be CPU- and memory-intensive, so larger hardware may
be needed for concurrent users, large datasets, or expensive local fitting
tools. Optional GPU-backed tools require a GPU Space and their corresponding
model assets.

## Local smoke test

```bash
docker build -t sr-harness-space .
docker run --rm -p 8000:8000 sr-harness-space
curl --fail http://127.0.0.1:8000/health
```
