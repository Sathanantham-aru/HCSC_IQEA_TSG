# IQEA — Azure container image.
#
# Every FROM below pins --platform=linux/amd64 explicitly. App Service Linux
# only runs amd64 - there is no ARM plan for it. Without this pin, `docker
# build` defaults to the BUILD MACHINE's own architecture (e.g. an Apple
# Silicon Mac or an arm64 CI runner produces an arm64 image), which then fails
# at container start with "exec /usr/local/bin/entrypoint.sh: exec format
# error" - a kernel-level architecture mismatch, not a bug in the script
# itself. Pinning here makes the build produce the right image regardless of
# what machine runs `docker build`.

# ── noVNC static client ──────────────────────────────────────────────────────
# Vendored at build time rather than proxied from a Chrome node's port 7900:
# node pod IPs are not reachable from outside the AKS cluster (only the Grid
# Hub is), and even where a node WAS reachable (App Service's single sidecar,
# Compose scaling) a fixed upstream meant every concurrent user's live view
# hit whichever ONE node happened to be there, not their own session — see
# nginx.conf.template and browser_factory.get_novnc_url() for the session-
# scoped fix this enables. Pinned tag, not @latest: this ships inside our own
# image, so an upstream noVNC change should not alter behaviour without us
# choosing to bump it.
# FROM --platform=linux/amd64 alpine:3.20 AS novnc
# RUN apk add --no-cache curl \
#     && curl -fsSL -o /tmp/novnc.tar.gz \
#          https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz \
#     && mkdir -p /novnc \
#     && tar -xzf /tmp/novnc.tar.gz -C /novnc --strip-components=1 \
#     && rm /tmp/novnc.tar.gz

# # Python 3.12 is a HARD requirement, not a preference: utilities/Utilities_Xpath.py
# # uses a backslash inside an f-string expression, which is only legal from 3.12
# # (PEP 701). On 3.11 the app dies with SyntaxError at import.
# FROM --platform=linux/amd64 python:3.12-slim

# ENV PYTHONUNBUFFERED=1 \
#     PYTHONDONTWRITEBYTECODE=1 \
#     # Modules do `from config...` / `from utilities...`; run_ai.bat sets
#     # PYTHONPATH=%CD% locally and the container needs the same.
#     PYTHONPATH=/app \
#     # protobuf's native "upb" extension segfaults and silently kills the
#     # Streamlit server (see the comment in run_ai.bat).
#     PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
#     # Switches the app to remote-browser + no-.env + desktop-recording-disabled.
#     # Override from App Service application settings without rebuilding.
#     IQEA_EXECUTION_TYPE=azure \
#     TESSERACT_CMD=/usr/bin/tesseract \
#     # App Service default: sidecar containers share a network namespace, so the
#     # Grid Hub is on localhost. Compose/K8s override this to a service name;
#     # AKS overrides it to the Hub's private IP/DNS name.
#     GRID_UPSTREAM=127.0.0.1:4444 \
#     SELENIUM_REMOTE_URL=http://127.0.0.1:4444/wd/hub

# RUN apt-get update && apt-get install -y --no-install-recommends \
#         # pytesseract shells out to this binary — without it every OCR call
#         # fails. This is the whole fix for "tesseract not working in azure".
#         tesseract-ocr tesseract-ocr-eng \
#         # opencv/scikit-image (PBI visual comparison) need these at import time
#         libgl1 libglib2.0-0 \
#         # nginx fronts both Streamlit and the Grid's noVNC on ONE port,
#         # because App Service exposes only one.
#         nginx supervisor \
#         # Node + npx: the self-healing DOM collector drives @playwright/mcp,
#         # which mcp_use launches via `npx -y @playwright/mcp@latest`. Without
#         # node in the image that flow fails with "npx: not found".
#         nodejs npm \
#         # envsubst — renders the Grid Hub address into nginx.conf at start
#         gettext-base \
#         curl ca-certificates \
#     && rm -rf /var/lib/apt/lists/*

# WORKDIR /app

# # ── MCP DOM collector (self-healing) ─────────────────────────────────────────
# # Self_healing_web_application/src/mcp_use_client.py runs the generated script
# # through @playwright/mcp to collect the DOM. That is a FULLY AUTOMATED step —
# # no human watches it — so it runs headless inside this container rather than
# # on the Chrome sidecar's display. Two things must be baked in:
# #   1. the MCP server package, so `npx` does not download it on every run
# #      (slow, and impossible if egress is restricted)
# #   2. Playwright's Chromium plus its system libraries
# # PLAYWRIGHT_BROWSERS_PATH puts the browser somewhere the app user can read.
# ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
#     NPM_CONFIG_UPDATE_NOTIFIER=false
# RUN npm install -g @playwright/mcp@latest \
#     && npx --yes playwright@latest install --with-deps chromium \
#     && npm cache clean --force \
#     # Fail the BUILD if the binary is not on PATH under the name the app calls
#     # (mcp_use_client._build_mcp_config). Better a broken build than a
#     # self-healing run that dies with "command not found" in production.
#     #
#     # @playwright/mcp RENAMED this executable: older versions shipped
#     # `mcp-server-playwright`, current ones ship `playwright-mcp`. Pinning the
#     # image to @latest means the name can move under us again, so print what
#     # the package actually installed before asserting the one the app calls —
#     # the two must be changed together.
#     && ls /usr/local/lib/node_modules/@playwright/mcp/package.json > /dev/null \
#     && node -e "console.log('@playwright/mcp bins:', Object.keys(require('/usr/local/lib/node_modules/@playwright/mcp/package.json').bin || {}).join(', '))" \
#     && command -v playwright-mcp \
#     && playwright-mcp --help > /dev/null

# # Dependencies first so code edits do not invalidate the pip layer.
# # The PEP 508 `sys_platform == "win32"` markers make pip skip pywin32 /
# # pywinauto / comtypes here; without them this step HARD-FAILS on Linux.
# COPY requirements.txt .
# RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
#     && pip install --no-cache-dir -r requirements.txt

# # .dockerignore keeps .env, .venv1/ and the *.tmp.* leftovers out of the image.
# COPY . .

# # ── Chromium for the DOM collector itself ────────────────────────────────────
# # The step above installed the browser for @playwright/mcp's bundled
# # playwright-core. The generated collector script is a SEPARATE Node process:
# # `node output/Dom_script/dom_collector_1.js` does `require('playwright')`,
# # which resolves to the copy committed at
# # Self_healing_web_application/node_modules (playwright 1.54.2 today), NOT to
# # the @latest used above. Playwright browsers are revision-pinned per version,
# # so 1.54.2 looks for /ms-playwright/chromium_headless_shell-1181 and dies with
# # "Executable doesn't exist" when only @latest's revision is present.
# #
# # This runs AFTER `COPY . .` because it installs whatever revision the
# # committed node_modules asks for — bump that copy and this step follows, with
# # no version to keep in step by hand. Both revisions live in /ms-playwright
# # side by side; the download is ~170MB.
# #
# # --with-deps is omitted deliberately: the apt libraries were installed above
# # and are revision-independent.
# # cli.js is invoked through node directly rather than through `npx playwright`
# # or node_modules/.bin/playwright: those shims are sh scripts committed from a
# # Windows checkout, and a CRLF shebang makes the kernel fail the exec with a
# # bare "not found" (the same trap as entrypoint.sh below).
# RUN cd /app/Self_healing_web_application \
#     && node -e "console.log('collector playwright:', require('playwright/package.json').version)" \
#     && node node_modules/playwright/cli.js install chromium \
#     && ls /ms-playwright

# COPY deploy/nginx.conf.template /etc/nginx/nginx.conf.template
# COPY deploy/supervisord.conf    /etc/supervisor/conf.d/iqea.conf
# COPY deploy/entrypoint.sh       /usr/local/bin/entrypoint.sh
# COPY --from=novnc /novnc/vnc.html /novnc/app /novnc/core /novnc/vendor /usr/share/novnc/
# # Normalise line endings — the repo is edited on Windows, and a CRLF shebang
# # makes the kernel fail the exec with a bare "not found".
# RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
#     && chmod +x /usr/local/bin/entrypoint.sh

# # App Service routes public traffic to this port (set WEBSITES_PORT=8000).
# EXPOSE 8000

# HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
#     CMD curl -fsS http://localhost:8000/_stcore/health || exit 1

# CMD ["/usr/local/bin/entrypoint.sh"]
FROM alpine:3.20 AS novnc

#FROM --platform=linux/amd64 alpine:3.20 AS novnc

RUN apk add --no-cache curl \
    && curl -fsSL -o /tmp/novnc.tar.gz \
       https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz \
    && mkdir -p /novnc \
    && tar -xzf /tmp/novnc.tar.gz \
       -C /novnc \
       --strip-components=1 \
    && rm -f /tmp/novnc.tar.gz


# ================================================================
# STAGE 2 - IQEA Application
# ================================================================
FROM  python:3.12-slim
#FROM --platform=linux/amd64 python:3.12-slim

# ================================================================
# ENVIRONMENT
# ================================================================
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    IQEA_EXECUTION_TYPE=azure \
    TESSERACT_CMD=/usr/bin/tesseract \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    SELENIUM_REMOTE_URL=http://127.0.0.1:4444/wd/hub


# ================================================================
# OS DEPENDENCIES
# ================================================================
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        libgl1 \
        libglib2.0-0 \
        nginx \
        supervisor \
        nodejs \
        npm \
        gettext-base \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*


# ================================================================
# APPLICATION DIRECTORY
# ================================================================
WORKDIR /app


# ================================================================
# COPY APPLICATION SOURCE
#
# IMPORTANT:
# docker-compose.yml uses:
#
#   context: ..
#   dockerfile: deploy/Dockerfile
#
# Therefore the build context is:
#
#   ai-accelerator/
#
# This copies:
#
#   ai-accelerator/IQEA.py
#
# to:
#
#   /app/IQEA.py
# ================================================================
COPY . /app


# ================================================================
# VERIFY APPLICATION
# ================================================================
RUN echo "============================================" \
    && echo "Checking IQEA.py" \
    && test -f /app/IQEA.py \
    && ls -lh /app/IQEA.py \
    && echo "IQEA.py found successfully" \
    && echo "============================================"


# ================================================================
# PLAYWRIGHT / MCP
# ================================================================
RUN npm install -g @playwright/mcp@latest \
    && npm install -g playwright@latest \
    && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
       playwright install --with-deps chromium \
    && npm cache clean --force


# ================================================================
# VERIFY PLAYWRIGHT
# ================================================================
RUN node --version \
    && npm --version \
    && npm list -g --depth=0 \
    && npm list -g @playwright/mcp \
    && npm list -g playwright \
    && test -d /ms-playwright


# ================================================================
# PYTHON DEPENDENCIES
# ================================================================
RUN pip install --no-cache-dir --upgrade \
        pip \
        setuptools \
        wheel \
    && pip install --no-cache-dir \
        -r /app/requirements.txt


# ================================================================
# COPY noVNC FROM STAGE 1
# ================================================================
COPY --from=novnc /novnc /usr/share/novnc


# ================================================================
# NGINX CONFIGURATION
# ================================================================
COPY deploy/nginx.conf.template \
     /etc/nginx/nginx.conf.template


# ================================================================
# SUPERVISOR CONFIGURATION
# ================================================================
COPY deploy/supervisord.conf \
     /etc/supervisor/conf.d/iqea.conf


# ================================================================
# ENTRYPOINT
# ================================================================
COPY deploy/entrypoint.sh \
     /usr/local/bin/entrypoint.sh


# ================================================================
# FIX WINDOWS CRLF
# ================================================================
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh


# ================================================================
# VERIFY IMPORTANT FILES
# ================================================================
RUN echo "============================================" \
    && echo "Checking deployment files" \
    && test -f /app/IQEA.py \
    && test -f /etc/nginx/nginx.conf.template \
    && test -f /etc/supervisor/conf.d/iqea.conf \
    && test -x /usr/local/bin/entrypoint.sh \
    && test -d /usr/share/novnc \
    && echo "IQEA.py             : OK" \
    && echo "nginx config        : OK" \
    && echo "supervisor config   : OK" \
    && echo "entrypoint.sh       : OK" \
    && echo "noVNC               : OK" \
    && echo "============================================"


# ================================================================
# PORT
# ================================================================
EXPOSE 8000


# ================================================================
# HEALTH CHECK
# ================================================================
HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=90s \
    --retries=3 \
    CMD curl -fsS http://localhost:8000/_stcore/health || exit 1


# ================================================================
# START IQEA
# ================================================================
CMD ["/usr/local/bin/entrypoint.sh"]
