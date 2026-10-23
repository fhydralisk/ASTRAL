# Deploying SRHarness on Hugging Face Spaces

SRHarness can run as a Hugging Face Docker Space using the repository's root
`Dockerfile`. The dedicated [Space README template](README.space.md) contains
its display settings and Docker configuration, including port `8000`.

Hugging Face reads these settings from the top of **its own repository's root
`README.md`**. The GitHub README stays focused on the project introduction.
See the [official Space configuration reference](https://huggingface.co/docs/hub/spaces-config-reference).

## 1. Create the Space

Create a new Space with the **Docker** SDK. A private Space is recommended when
the deployment uses an owner-funded model API key. Use a separate checkout for
the Space. From the SRHarness repository, export the committed source and install
the Space-specific README before committing the deployment:

```bash
git clone https://huggingface.co/spaces/OWNER/SPACE_NAME ../srharness-space
git archive HEAD | tar -x -C ../srharness-space
cp ../srharness-space/deploy/huggingface/README.space.md ../srharness-space/README.md
git -C ../srharness-space add .
git -C ../srharness-space commit -m "Deploy SRHarness"
git -C ../srharness-space push
```

When updating an existing Space checkout, synchronize the committed project
files, including removing files deleted upstream, and reapply the README template
before committing. Keep any Space-specific metadata customizations in that
checkout. Do not push the GitHub branch directly to the Space: its README does
not contain the configuration Hugging Face needs.

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

## 2. Publish automatically from GitHub

The [Publish Hugging Face Space workflow](../../.github/workflows/publish-huggingface.yml)
runs when the version in `pyproject.toml` changes on `master`, alongside the PyPI
and Docker Hub workflows. It can also be started manually from GitHub Actions to
redeploy the current version.

Publishing uses [Hugging Face Trusted Publishers](https://huggingface.co/docs/hub/trusted-publishers)
with OIDC. No personal access token or `HF_TOKEN` GitHub secret is needed.

In the target Space's **Settings → Trusted Publishers**, add **GitHub Actions**
with all three exact GitHub OIDC claim restrictions:

| Setting | Value |
| --- | --- |
| Repository (`repository`) | `yuzhTHU/SRHarness` |
| Branch (`ref`) | `refs/heads/master` |
| Workflow (`workflow_ref`) | `yuzhTHU/SRHarness/.github/workflows/publish-huggingface.yml@refs/heads/master` |

Use the Space-level trusted publisher, not the account-level CI/CD identity
(which provides different, read-oriented permissions). Each matching workflow
run receives a short-lived token with write access to this Space only.

The workflow has `id-token: write` permission and sets
`HF_OIDC_RESOURCE=spaces/YuMeow/SRHarness`; the Hugging Face client exchanges the
GitHub identity for a temporary publishing credential. The credential is never
printed or saved as a GitHub secret. An exchange failure stops deployment.

For another deployment, set the optional GitHub Actions variables `HF_SPACE_ID`
and `HF_SPACE_URL` (defaults: `YuMeow/SRHarness` and
`https://yumeow-srharness.hf.space`) and register a trusted publisher on that Space.

After saving the trust rule, open **GitHub Actions → Publish Hugging Face Space →
Run workflow**, select `master`, and run it once to verify the authorization and
deployment. Subsequent version changes on `master` trigger it automatically.

The workflow exports the selected Git commit, uploads only the application source
and Docker build inputs, and installs the dedicated Space README. It removes
obsolete files under `src/` while preserving other Space repository files and
settings. Local experiments and uncommitted work are excluded.

After uploading, it waits for the running commit to match the uploaded commit,
for `/api/version` to report the expected version, and for `/health` to pass. A failed build or an unsuccessful startup makes
the workflow fail. The public application entry is
<https://yumeow-srharness.hf.space/>.

## 3. Configure model credentials

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

## 4. Choose a storage policy

The image writes conversations, uploaded data, settings, and run artifacts to
`/data`.

- Without persistent storage, Space restarts can erase `/data`.
- To retain work, attach persistent storage or a writable Storage Bucket at
  `/data` in the Space settings.
- Persisted workspaces can contain user-uploaded data and provider keys entered
  through the WebUI. Use a private Space for sensitive work and apply an
  appropriate retention policy.

## 5. Resource expectations

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
