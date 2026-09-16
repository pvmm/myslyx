"""Deployment detection: is Myslyx serving a local (single-developer) session?

The plugin contract lets a plugin declare ``"onlyLocal": true`` so it only
activates when the editor runs on a local machine (see
``static/plugins/README.md``). The page publishes the value to the client as
``window.__wbLocal`` (``pages/editor_page.py``); this module is where the
server decides it.

Local by default; "remote" when the process looks like a shared Hugging Face
Space deployment. An operator may force either side with ``MYSLYX_LOCAL``.
"""

import os

_HF_SPACE_VARS = ('SPACE_ID', 'HF_SPACE_ID', 'SPACE_HOST')


def is_local() -> bool:
    """True when Myslyx runs locally, False for a shared deployment.

    Resolution order:
      1. ``MYSLYX_LOCAL`` set to 0/1 (or true/false/yes/no/on/off) wins;
      2. otherwise belong to a Hugging Face Space (any of the Space env vars);
      3. otherwise local.
    """
    override = os.environ.get('MYSLYX_LOCAL')
    if override is not None:
        return override.lower().strip() in ('1', 'true', 'yes', 'on')
    return not any(os.environ.get(name) for name in _HF_SPACE_VARS)