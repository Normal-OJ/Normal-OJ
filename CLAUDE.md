# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is a **meta-repository** that orchestrates the full Normal-OJ stack via Docker Compose. The three subdirectories are **git submodules**, each with its own toolchain, README, and CI:

- `Back-End/` — Flask REST API (Python 3.11, Poetry). Submodule: `Normal-OJ/Back-End`.
- `new-front-end/` — Vue 3 + TypeScript SPA (pnpm, Vite). Submodule: `Normal-OJ/new-front-end`.
- `Sandbox/` — Code-execution service (Python 3.10/3.13, pip). Submodule: `Normal-OJ/Sandbox`.

After cloning, run `git submodule foreach --recursive git checkout main` — submodules are detached by default and need to be put back on `main` before any work.

## Running the full stack

Compose layers: `docker-compose.yml` (base) is always merged with `docker-compose.override.yml` (dev — adds the Vue dev server, MinIO sidecar, mounts source for hot reload, switches Back-End to its `development` build target). Production uses `docker-compose.prod.yml` instead (different Caddyfile, `.secret/*.env`, no source mounts).

```bash
mkdir -p ./Back-End/minio/data    # one-time; MinIO bind-mount target
cd Sandbox && ./build.sh && cd .. # one-time; builds noj-c-cpp + noj-py3 images, downloads sandbox binary
# then update Sandbox/.config/submission.json: set "working_dir" to the absolute path of Sandbox/submissions

docker compose up -d              # start everything
docker compose up --build -d      # rebuild images first
./deploy.sh                       # production: rebuild --no-cache, down, up with prod overlay
```

Default URLs in dev: app at `http://localhost:8080`, MinIO console at `http://localhost:9001`, mongo-express at `http://localhost:8081`. Bootstrap admin: `first_admin` / `firstpasswordforadmin` (created on first backend boot in `Back-End/app.py`).

MinIO is required only for problem/submission features. The override file uses `network_mode: "service:web"` so MinIO shares the web container's network namespace — this is intentional: presigned URLs must start with `localhost:9000` to be reachable from the browser, not `minio:9000`.

## Architecture

```
browser ──► Caddy (:8080) ──► Vue dev server (vue:5173)         frontend assets
                          └─► Flask web (web:8080)              REST API under /api
                                  ├──► MongoDB                  primary store (mongoengine)
                                  ├──► Redis                    cache / rate limiting
                                  ├──► MinIO                    submission source + outputs (S3 API)
                                  └──► Sandbox (HTTP POST /submit/<id>)
                                            └─► Docker engine   one container per testcase
                                            └─► PUT /api/submission/<id>/complete  (callback)
```

`SANDBOX_TOKEN` is a shared secret used in both directions between Back-End and Sandbox (see `mongo/sandbox.py` on the backend, `dispatcher/config.py` on the sandbox). The Caddyfile (`/.config/Caddyfile`) does the `/api/*` → `web:8080` rewrite; everything else proxies to the Vue dev server.

### Back-End (Flask)

`Back-End/app.py` is the app factory — it registers ~13 blueprints (one per resource: `auth`, `profile`, `problem`, `submission`, `course`, `homework`, `test`, `ann`, `ranking`, `post`, `copycat`, `health`, `user`) and seeds `first_admin` + the `Public` course on first run. Two-layer code structure:

- `model/` — Flask blueprints (HTTP layer). `model/schemas/` holds Pydantic request bodies; `model/utils/` has decorators like `@parse_body`, `@login_required`, plus SMTP helpers.
- `mongo/` — Domain layer wrapping `mongoengine` documents. `mongo/engine.py` defines schemas and connects to MongoDB (uses `mongomock` automatically when `MONGO_HOST` starts with `mongomock://`). Resource modules (`mongo/problem/`, `mongo/submission.py`, etc.) wrap engine documents in higher-level classes used by the blueprints.

Migrations live in `Back-End/migrations/` (mongoengine scripts) — separate from the Go program `Back-End/migrate.go`, which is a one-shot CLI for triggering per-submission `migrate-code` / `migrate-output` API calls during data backfills.

### Sandbox

Single Flask process (`Sandbox/app.py`) exposes `POST /submit/<id>` and `GET /status`. Inside, a long-running `Dispatcher` thread (`dispatcher/dispatcher.py`) owns a bounded `queue.Queue` of `Compile`/`Execute` jobs and spawns a worker thread per testcase that launches a Docker container (`runner/submission.py` + `runner/sandbox.py` + the `sandbox` binary downloaded by `build.sh`). The dispatcher tracks per-submission locks and compile results, then `PUT`s the aggregated result back to the backend's `/submission/<id>/complete` and cleans up via `file_manager`. C/C++ submissions go through a compile job first; Python skips that step.

Languages map by integer ID: `0=c11`, `1=cpp17`, `2=python3`. Two Docker images do the actual execution: `noj-c-cpp` and `noj-py3` (built by `Sandbox/build.sh`).

### new-front-end

Vue 3 + Pinia + vue-router + TailwindCSS + DaisyUI. **File-based routing** via `vite-plugin-pages` — `src/pages/foo.vue` ⇒ `/foo`, `src/pages/foo/[id].vue` ⇒ `/foo/:id`. Other directories follow the README's convention: `src/components/` (shared UI), `src/composables/` (reusable logic), `src/models/` (API client per resource), `src/stores/` (Pinia), `src/i18n/` (en + zh-TW required for any new string), `src/types/`, `src/utils/`. Auto-generated files land in `src/auto/` (do not edit).

Auth gate lives in `src/router.ts` — `publicPages` regex list is the allowlist; everything else redirects unauthenticated users to `/`. Vite proxies `/api` to `https://api.noj.tw` (or `https://dev.noj.tw` when `NODE_ENV=test`) for standalone dev outside Docker; in Docker, Caddy handles the proxy instead.

`pnpm` is mandatory — `preinstall` script blocks npm/yarn. Node version is pinned by `.node-version` (22).

## Commands

### Back-End (cd Back-End)

```bash
poetry install                                         # one-time
poetry run pytest                                      # full suite (uses mongomock + testcontainers MinIO + fakeredis)
poetry run pytest tests/test_problem.py                # one file
poetry run pytest tests/test_problem.py::test_func     # one test
poetry run pytest --cov=./ --cov-config=.coveragerc    # with coverage (matches CI)
poetry run yapf -ir .                                  # format in place
poetry run yapf --recursive --parallel --diff .        # check only (matches CI)
poetry run pre-commit install                          # set up commit hooks (yapf + basic checks)
```

CI (`.github/workflows/continuous-integration-workflow.yml`) runs the diff-mode yapf and pytest with coverage on PRs to `main`.

### new-front-end (cd new-front-end)

```bash
pnpm install                          # one-time (Node 22, pnpm 10.6.1)
pnpm dev                              # Vite dev server
pnpm build                            # vue-tsc type check + production build
pnpm test                             # vitest unit tests
pnpm lint                             # eslint + prettier --check
pnpm format                           # prettier --write
pnpm exec playwright test             # E2E (requires app running at http://localhost:3000)
pnpm exec playwright test --ui        # interactive runner
pnpm exec playwright install --with-deps   # one-time browser install
```

Playwright config (`playwright.config.ts`) auto-starts `pnpm preview --port 3000` with `NODE_ENV=test` so tests hit `https://dev.noj.tw` via the Vite proxy. CI (`lint-ci.yaml`) runs `pnpm lint` + `pnpm test`; `playwright.yml` runs E2E.

### Sandbox (cd Sandbox)

```bash
./build.sh                            # build noj-c-cpp + noj-py3 images, fetch sandbox binary
pip install -r requirements.txt       # runtime deps
pip install -r tests/requirements.txt # test deps
pytest -v                             # full suite (requires ./build.sh first — tests spawn real containers)
pytest tests/test_dispatcher.py       # one file
yapf . -rd                            # check only (matches CI)
yapf -ir .                            # format in place
```

Sandbox CI uses Python 3.10. The runtime container uses Python 3.13 (see `Dockerfile`). Backend uses Python 3.11. Be aware of these version differences when editing shared utilities.

## Conventions worth noting

- **Commit style**: front-end CONTRIBUTING.md mandates [conventional commits](https://www.conventionalcommits.org/) and `feat/`, `fix/`, `refactor/` branch prefixes. Existing commits in this meta-repo follow the same convention.
- **Submodule pointers**: editing a submodule and committing inside it updates *that submodule's* HEAD; bumping the pointer in this meta-repo is a separate commit at the root. Be deliberate about which repo you're committing to.
- **Secrets**: production env files live in `.secret/` (gitignored). `.secret.example/` shows the required keys for `caddy.env`, `mongo-express.env`, `sandbox.env`, `web.env`.
- **Logs**: `Back-End/logs/` and `Sandbox/logs/` are bind-mounted in the prod compose file. `gunicorn_error.log` is also bind-mounted on the backend.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (`Normal-OJ/Normal-OJ`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
