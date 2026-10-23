# IQEA — Azure deployment notes

Handover notes for the DevOps team. The application side of this work is done;
what remains is hosting.

## The shape

```
user ──HTTPS (one port)──► nginx (main container)
                             ├─ /            → Streamlit :8501         (same container)
                             ├─ /vnc/        → vendored noVNC static client (same container)
                             └─ /session/... → Selenium Grid Hub :4444
                                                 └─ chrome nodes: Xvfb + fluxbox
                                                    + HEADED Chrome + VNC
```

Chrome runs **headed on a virtual display**, not headless. Headless starts fine
but leaves nothing for a user to interact with, and interactive action recording
is IQEA's core feature. Users see and drive that Chrome through noVNC embedded
in the page.

Selenium Grid proxies each session's screen keyed by **session id**
(`/session/<id>/se/vnc`), so one fixed upstream (the Hub) still lands every
concurrent user on their own screen — `browser_factory.get_novnc_url()` bakes
the driver's session id into that path per user.

## Non-negotiables

| Requirement | Why |
|---|---|
| **Python 3.12+** base image | `utilities/Utilities_Xpath.py` uses a backslash in an f-string expression (PEP 701). 3.11 dies with SyntaxError at import. |
| **`PYTHONPATH=/app`** | Modules do `from config...` / `from utilities...`; `run_ai.bat` sets this locally. |
| **`PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python`** | The native protobuf extension segfaults and silently kills Streamlit. |
| **`--shm-size=2g` on Chrome nodes** | `/dev/shm` defaults to 64 MB; Chrome crashes on heavy pages. |
| **`Upgrade`/`Connection` headers in nginx** | Streamlit *and* noVNC are both WebSocket. Without these, Streamlit hangs on "Please wait" and noVNC shows a grey frame — with no error in either case. |
| **`SE_SESSION_TIMEOUT`** | Users close tabs without stopping. Without server-side reaping, dead sessions pin nodes and starve everyone. |
| **`SE_NODE_MAX_SESSIONS=1`** | Two sessions on one node share one X display — users would see and click each other's browser. |
| **`.env` must not enter the image** | Several call sites use `load_dotenv(override=True)`, where the FILE beats real env vars. A stray `.env` would silently override App Service settings. `.dockerignore` and `config/env_loader.py` both guard this. |

## Hosting choice — please read

**App Service cannot scale browsers dynamically.** Sidecar containers are declared
statically, so the node count is fixed at whatever is configured. Since every
user needs their own browser, that fixed number is the hard ceiling on concurrent
recording.

For genuinely dynamic capacity:

- **Azure Container Apps** (recommended) — KEDA ships a `selenium-grid` scaler
  that scales nodes off the Grid's pending-session queue, including to zero.
- **AKS** — same via the Selenium Grid Helm chart.
- **App Service** — workable only with a fixed node count sized to peak demand.

Capacity rule of thumb: **~1 GB RAM per concurrent Chrome**, plus the app.

## App Service / Container Apps settings

Target confirmed: **App Service, Linux, East US** —
`iqea-poc-cweseafae3a9bvgf.eastus-01.azurewebsites.net`, served at the **root path**
(so `/vnc/` needs no prefix adjustment).

| Setting | App Service value | Compose / K8s value |
|---|---|---|
| `WEBSITES_PORT` | `8000` | — |
| `IQEA_EXECUTION_TYPE` | `azure` | `azure` |
| `SELENIUM_REMOTE_URL` | `http://127.0.0.1:4444/wd/hub` | `http://chrome:4444/wd/hub` |
| `GRID_UPSTREAM` | `127.0.0.1:4444` | `chrome:4444` |
| `TESSERACT_CMD` | `/usr/bin/tesseract` | same |
| `IQEA_NOVNC_PATH` | `/vnc/` | same |
| secrets (`AZURE_OPENAI_API_KEY`, Jira, GitLab…) | application settings — **not** a `.env` | env |

> **App Service sidecars share a network namespace.** They reach each other on
> `127.0.0.1`, *not* by container name. A Compose-style `chrome:4444` fails there
> with `host not found in upstream` and nginx refuses to start. The image defaults
> to localhost for exactly this reason; `deploy/entrypoint.sh` renders the value
> into the nginx config at container start, so nothing needs rebuilding to change it.

`IQEA_EXECUTION_TYPE` overrides `config/settings.ini`, so modes can be flipped
from the portal without a rebuild.

## Try it locally first

```bash
docker compose -f deploy/docker-compose.yml up --build
# app        → http://localhost:8000
# grid       → http://localhost:4444
# more seats → docker compose -f deploy/docker-compose.yml up --scale chrome-node=5
```

This runs the exact Azure code path on a laptop. Please get this working before
deploying — container issues are far cheaper to diagnose here.

## Still open

- **Change `SE_VNC_PASSWORD`** from the placeholder in `docker-compose.yml`.
- **~~Confirm the noVNC embed path~~** — resolved via `kubectl exec ... curl
  http://selenium-hub:4444/status`, which reported each session's
  `se:vnc: ws://<node>:4444/session/<id>/se/vnc`. `get_novnc_url()` now builds
  exactly that path; see `deploy/AKS_GRID_HANDOVER.txt` A4.
- **Authentication.** Anyone who reaches `/vnc/` can drive a browser. Put Azure
  AD / Easy Auth in front before this is reachable beyond the team.
