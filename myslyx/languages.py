"""Language catalog and the ``MYSLYX_DISABLED_LANGS`` deployment gate.

Languages are the stored CodeMirror values offered by the LANG combo box
(``pages/editor_page.py``). An operator may hide a subset of them per
deployment by setting an environment variable::

    MYSLYX_DISABLED_LANGS="C MSXgl, Pascal"

The value is a comma-separated list (language keys contain spaces, so commas
are the separator). Each token is matched case-insensitively against BOTH the
stored language key (``"C MSXgl"``) and its base-language family (``"c"``), so
``c`` disables every C-derived dialect while ``C MSXgl`` disables only that
one. Disabled languages disappear from the LANG combo box, and plugins scoped
to them (via ``languages`` or ``baseLang`` in their ``plugin.json``) are
disabled and greyed out in the PLUGINS menu (see ``static/plugins.js`` /
``static/settings-menu.js``).

The tables live here so the page and the gate share one source of truth.
"""

import os

# Language options offered by the LANG combo box. Keys are the values stored
# with files (CodeMirror language names), values are the labels shown there.
LANGUAGES: dict[str, str] = {
    # HitBasic is a BASIC dialect. Its CodeMirror language support ships as a
    # plugin (static/plugins/hitbasic/): it builds on the VBScript highlighter
    # and declares "'" as the line-comment token, so Ctrl-/ works in BASIC.
    'HitBasic': 'HitBasic',
    'Pascal': 'Pascal',
    # Pascal with Kari Lammassaari's Turbo Pascal 3 MSX routine library. Shares
    # the CodeMirror 'Pascal' mode; only the hints (static/hints/lammassaari.json)
    # differ.
    'Pascal Lammassaari': 'Pascal+Lammassaari',
    'C': 'C',
    # C with the MSXgl engine API (SDCC/ZX81-style fixed-width types). Shares
    # the CodeMirror 'C' mode; only the hints (static/hints/msxgl.json) differ.
    'C MSXgl': 'C+MSXgl',
    'Z80': 'Z80 Assembly',
    'Text': 'Text',
}

# Default language for newly created files. The LANG combo box mirrors the
# language of the currently visible file (see _load_file_into_editor), so
# new files keep this fixed default instead of inheriting the active file's.
DEFAULT_LANG = 'HitBasic'

# Stored language ids that once existed in LANGUAGES but are no longer
# offered by the combo box. Files saved with such an id keep working: they
# resolve to the current id instead of falling back to plain text.
LEGACY_LANGUAGES: dict[str, str] = {
    'VBScript': 'HitBasic',
}

# Maps stored CodeMirror language values to hint dictionary keys (files under
# static/hints/<key>.json). Unknown languages fall back to plain text.
HINT_KEYS: dict[str, str] = {
    'HitBasic': 'hitbasic',
    'Pascal': 'pascal',
    'Pascal Lammassaari': 'lammassaari',
    'C': 'c',
    'C MSXgl': 'msxgl',
    'Z80': 'plaintext',
    'Text': 'plaintext',
}

# Base-language attribute: the normalized family/dialect a language belongs
# to, shared by every variant of the same base (plain C and the MSXgl C
# framework both are 'c'). Plugins scope on this with "baseLang": ["c"] so a
# future C-derived framework only needs entries here (and in LANGUAGES) to be
# picked up automatically.
BASE_LANG: dict[str, str] = {
    'HitBasic': 'basic',
    'Pascal': 'pascal',
    'Pascal Lammassaari': 'pascal',
    'C': 'c',
    'C MSXgl': 'c',
    'Z80': 'asm',
    'Text': 'text',
}

# The environment variable that hides languages for a deployment.
DISABLED_LANGS_ENV = 'MYSLYX_DISABLED_LANGS'


def _cm_mode(lang: str) -> str:
    """Map a stored language value to the CodeMirror mode to use.

    MSXgl is a C framework, so 'C MSXgl' keeps the 'C' syntax highlighting.
    Kari Lammassaari's dialect is plain Turbo Pascal, so it keeps 'Pascal'.
    Any other stored value is already a valid CodeMirror mode name.
    """
    if lang == 'C MSXgl':
        return 'C'
    if lang == 'Pascal Lammassaari':
        return 'Pascal'
    return lang


def _canonical_lang(lang: str | None) -> str | None:
    """Resolve a stored language value to a current LANGUAGES key.

    Returns None only for values that were never a real language id.
    """
    if lang in LANGUAGES:
        return lang
    return LEGACY_LANGUAGES.get(lang) if lang is not None else None


def _disabled_tokens() -> set[str]:
    """Normalized tokens from ``MYSLYX_DISABLED_LANGS``.

    Read on every call (no caching) so a test phase can set the variable and
    the page render picks it up without a process restart.
    """
    raw = os.environ.get(DISABLED_LANGS_ENV, '')
    return {tok.strip().lower() for tok in raw.replace('\n', ',').split(',') if tok.strip()}


def is_lang_disabled(lang: str | None) -> bool:
    """True when ``lang`` (or its base family) is disabled for this run.

    A token matching the language key disables just that dialect; a token
    matching the base family disables every dialect sharing it.
    """
    if not lang:
        return False
    tokens = _disabled_tokens()
    if not tokens:
        return False
    if lang.lower() in tokens:
        return True
    base = BASE_LANG.get(lang)
    return bool(base and base.lower() in tokens)


def enabled_languages() -> dict[str, str]:
    """LANGUAGES minus the disabled entries, preserving declaration order."""
    enabled = {key: label for key, label in LANGUAGES.items() if not is_lang_disabled(key)}
    if not enabled:
        raise ValueError(
            f'{DISABLED_LANGS_ENV} hides every language; leave at least one enabled')
    return enabled


def validate_disabled_langs() -> None:
    """Fail fast when ``MYSLYX_DISABLED_LANGS`` would hide every language."""
    enabled_languages()


def disabled_languages() -> list[str]:
    """Disabled LANGUAGES keys, in declaration order (for the client)."""
    return [key for key in LANGUAGES if is_lang_disabled(key)]


def disabled_base_langs() -> list[str]:
    """Base families with no enabled language left (for plugin scoping)."""
    bases: dict[str, list[str]] = {}
    for key, base in BASE_LANG.items():
        bases.setdefault(base, []).append(key)
    return [base for base, keys in bases.items()
            if keys and all(is_lang_disabled(key) for key in keys)]


def resolve_lang(lang: str | None) -> str:
    """Resolve a stored value to an enabled language key, for loading a file.

    Legacy ids are migrated first (via ``_canonical_lang``). A disabled or
    unknown value falls back to another enabled dialect of the same base (e.g.
    disabling ``C MSXgl`` keeps its files opening as plain ``C``), then to
    ``Text``, then to any enabled language. Never returns a disabled key.
    """
    canon = _canonical_lang(lang)
    if canon is not None and not is_lang_disabled(canon):
        return canon
    if canon is not None:
        base = BASE_LANG.get(canon)
        for key in LANGUAGES:
            if key != canon and BASE_LANG.get(key) == base and not is_lang_disabled(key):
                return key
    if not is_lang_disabled('Text') and 'Text' in LANGUAGES:
        return 'Text'
    return next(iter(enabled_languages()), 'Text')

