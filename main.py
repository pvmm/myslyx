import os
from nicegui import app, ui

# Register pages (importing triggers @ui.page decorator registration)
import pages.home_page  # noqa: F401
import pages.editor_page  # noqa: F401

# Serve static files
app.add_static_files('/static', os.path.join(os.path.dirname(__file__), 'static'))

ui.run(title='HITBASIC Editor', host='0.0.0.0', port=8080, reload=True)
