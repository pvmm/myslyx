import os
import sys
from pathlib import Path


def user_plugins_dir() -> Path:
    """Cross-platform user configuration directory for plugins.

    Resolved per operating system:
      Windows: %APPDATA%\\myslyx\\plugins
      macOS:   ~/Library/Application Support/myslyx/plugins
      Linux:   $XDG_CONFIG_HOME/myslyx/plugins (default ~/.config/myslyx/plugins)
    """
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
    elif sys.platform == 'darwin':
        base = str(Path.home() / 'Library' / 'Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    return Path(base) / 'myslyx' / 'plugins'