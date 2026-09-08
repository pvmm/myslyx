import argparse
import logging
import os
import sys
from pathlib import Path

from nicegui import app, ui

# Register pages (importing triggers @ui.page decorator registration)
import myslyx.pages.home_page  # noqa: F401
import myslyx.pages.editor_page  # noqa: F401

# Serve the bundled static files (favicons, JS/CSS, hints, plugins).
app.add_static_files('/static', str(Path(__file__).resolve().parent / 'static'))

# Register a run config at import time so that uvicorn's auto-reload worker (a
# spawned process that re-imports this module before serving) passes NiceGUI's
# "You must call ui.run()" startup check. The real ui.run() in run() overrides
# these values, so this only affects reload workers and never starts a server.
app.config.add_run_config(
    reload=False,
    title='Myslyx Text Editor',
    viewport='width=device-width, initial-scale=1',
    favicon=None,
    dark=False,
    language=None,
    binding_refresh_interval=0.1,
    reconnect_timeout=3.0,
    message_history_length=1000,
    tailwind=True,
    unocss=None,
    prod_js=True,
    show_welcome_message=True,
    markdown=False,
)

# Quiet mode for the browser test harness (tests/runner.py): single process,
# no verbose logging.
_TESTING = os.environ.get('WB_TESTING') == '1'

if _TESTING:
    logging.basicConfig(level=logging.WARNING)
else:
    # Configure root logger and enable verbose logging for engineio/socketio to help reproduce the
    # KeyError:'REQUEST_METHOD' when it happens. This is diagnostic and can be
    # removed once the root cause is found.
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('engineio').setLevel(logging.DEBUG)
    logging.getLogger('socketio').setLevel(logging.DEBUG)
    logging.getLogger('uvicorn.error').setLevel(logging.DEBUG)


# Simple HTTP middleware to log incoming HTTP request methods and paths.
@app.middleware('http')
async def _log_requests(request, call_next):
    if not _TESTING:
        try:
            logging.debug(f"HTTP request: {request.method} {request.url}")
        except Exception:
            logging.exception('Failed to log request')
    return await call_next(request)


# Disable auto-reload to avoid multi-process reloader issues during debugging.
# Set `reload=True` only when actively developing and comfortable with the
# reloader behavior.
def _get_server_options() -> tuple[str, int, bool]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-p', '--port', type=int, help='Port to run the server on')
    parser.add_argument('-H', '--host', type=str, help='Host/interface to bind to')
    parser.add_argument('--no-reload', action='store_true', help='Disable uvicorn auto-reload')
    args, _ = parser.parse_known_args()
    env_port = os.environ.get('PORT')
    env_host = os.environ.get('HOST') or os.environ.get('WB_HOST')
    port = 8080
    host = '0.0.0.0'
    if env_port:
        try:
            port = int(env_port)
        except ValueError:
            logging.warning('Invalid PORT env var, falling back to CLI/default')
    if args.port:
        port = int(args.port)
    if env_host:
        host = env_host
    if args.host:
        host = args.host
    is_dash_m_package = Path(sys.argv[0]).name == '__main__.py' and (Path(sys.argv[0]).parent / '__init__.py').is_file()
    reload_enabled = not _TESTING and not args.no_reload and not is_dash_m_package
    if is_dash_m_package and not args.no_reload and not _TESTING:
        logging.warning('Auto-reload is not supported with `python -m myslyx` (NiceGUI limitation); running without it.')
    return host, port, reload_enabled


def run() -> None:
    """Launch the Myslyx server (uvicorn auto-reload unless --no-reload or `python -m`)."""
    host, port, reload_enabled = _get_server_options()
    ui.run(
        title='Myslyx Text Editor',
        host=host,
        port=port,
        reload=reload_enabled,
        uvicorn_reload_includes='*.py, *.css, *.js',
    )


if __name__ == '__main__':
    run()