# Storyboard Workflow Automation

An independent, sanitized and runnable Python technical demonstration derived from a privately developed AI short-drama workflow. This edition retains selected analysis, schema validation, runtime budgeting, asset matching and review modules, alongside a local Flask workflow and Playwright browser adapter. It uses fictional sample data and excludes private production endpoints, credentials, browser sessions and business assets.

## Runnable features

- Deterministic English script-to-shot mock analysis.
- Local Flask draft creation, inspection and explicit human approval, held in memory.
- Original structured storyboard models and validation, asset matching and review utilities (library APIs).
- Original OpenAI structured-output adapter with injectable client and environment-based configuration. No live API call is included in validation.

## Demonstration boundaries

The Flask app is a local demonstration, without authentication, durable storage or production hardening. The Playwright adapter targets only this local demo. Original private platform selectors, endpoints, credentials and production integrations are excluded. Mock analysis does not represent AI directing quality. Image generation and video rendering are not included. A full asset-management UI and production adapters remain future work in this edition.

## Run on Python 3.11 or newer

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m playwright install chromium
.venv\Scripts\python -m unittest discover -s tests
.venv\Scripts\python -m juemeng_auto.demo
```

Open http://127.0.0.1:5050 and paste examples/episode.txt. The JSON response contains a draft id; approve it with POST /approve/<id>. A duplicate script recreates its draft and resets approval. Restarting clears all drafts.

For optional browser execution install Chromium with `python -m playwright install chromium`, launch the local app and call `submit_demo(page, "http://127.0.0.1:5050/", script)` with a Playwright page. The browser integration test starts and stops its own loopback server on port 5050; stop an existing demo server before running the tests. It blocks external browser requests and uses an isolated browser context.

For optional LLM use configure OPENAI_API_KEY and a model you have access to. The original adapter accepts these values explicitly; the local Flask demo always uses mock analysis. Do not send confidential scripts. The public adapter suppresses provider diagnostics and chained exceptions; it does not save request or response bodies on failure.

See docs/architecture.md and SECURITY.md for module boundaries and safe local use. This repository is a standalone technical demonstration; it does not provide access to the original production system. No license has been selected for this edition.

The demo rejects non-object JSON, oversized input and cross-origin writes, restricts the Host header to the loopback demo address, and caps in-memory drafts at 100. It remains a single-process local demonstration, not a hosted multi-user application. Tests exercise LLM success, invalid structured output and recovery through an injected client without network requests or API charges.

For the independent secret scanner, install development dependencies with `.venv\Scripts\python -m pip install -r requirements-dev.txt`. Run `.venv\Scripts\detect-secrets scan --all-files --no-verify --exclude-files "(^|[/\\])(?:\.venv|__pycache__|build|dist|[^/\\]+\.egg-info)([/\\]|$)" .` to print results without writing a baseline. This scanner does not prove copyright ownership or detect all sensitive business context.
