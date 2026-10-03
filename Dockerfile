# Single-process NiceGUI production image. No Node toolchain needed: the
# in-browser LSP worker (worker.bundle.js) ships prebuilt inside the wheel.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Shared deployment (as on the Hugging Face Space): disables local-only
    # plugins and the machine-LSP bridge, and hides the HitBasic language
    # (see myslyx/languages.py). Overridable at run/deploy time.
    MYSLYX_LOCAL=0 \
    MYSLYX_DISABLED_LANGS="HitBasic" \
    PORT=8080

WORKDIR /app

# Install the package non-editable so the bundled static files (JS/CSS,
# hints, plugins, STARTUP.txt) ship inside the image via MANIFEST.in.
COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY myslyx ./myslyx
COPY main.py ./
RUN pip install --no-cache-dir .

EXPOSE 8080

# --no-reload: the uvicorn auto-reloader is a dev tool; production serves a
# single quiet process. Host/port come from $HOST/$PORT (fly sets PORT).
CMD ["myslyx", "--no-reload"]
