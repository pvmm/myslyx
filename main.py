import os
import argparse
import logging
from nicegui import app, ui

# Register pages (importing triggers @ui.page decorator registration)
import pages.home_page  # noqa: F401
import pages.editor_page  # noqa: F401

# Serve static files
app.add_static_files('/static', os.path.join(os.path.dirname(__file__), 'static'))

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
    reload_enabled = not _TESTING and not args.no_reload
    return host, port, reload_enabled


HOST, PORT, RELOAD = _get_server_options()
# Auto-reload via uvicorn when code or static files change during development.
# Disabled with --no-reload (or WB_TESTING=1) for the browser test harness.
ui.run(
    title='Myslyx Text Editor',
    host=HOST,
    port=PORT,
    reload=RELOAD,
    uvicorn_reload_includes='*.py, *.css, *.js',
)
