"""i18n: lightweight stdlib + dict catalog translation layer.

Public API: ``_(key, **kwargs)`` looks up a translated template (formatted
with the given kwargs) for the active language.

Resolution priority for the initial language (highest first):
  1. ``MISSKEY_CLI_LANG`` env var
  2. value persisted in the ``app_config`` table
  3. ``LANG`` env var, first two letters
  4. ``DEFAULT_LANG`` (``"en"``)
"""
import os

from .catalogs import en, ja, fr


DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "ja", "fr")

_CATALOGS = {
    "en": en.CATALOG,
    "ja": ja.CATALOG,
    "fr": fr.CATALOG,
}

_current_lang = DEFAULT_LANG
_current_catalog = _CATALOGS[DEFAULT_LANG]


def _(key, **kwargs):
    """Look up a translation key and format it with the given kwargs.

    Falls back current language → en → key itself, so a missing key surfaces
    visibly without crashing the CLI.
    """
    template = _current_catalog.get(key)
    if template is None:
        template = _CATALOGS[DEFAULT_LANG].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def get_language():
    return _current_lang


def _apply_language(code):
    """Swap the active catalog. Unknown codes silently fall back to en."""
    global _current_lang, _current_catalog
    if code not in _CATALOGS:
        code = DEFAULT_LANG
    _current_lang = code
    _current_catalog = _CATALOGS[code]


def _load_stored_language():
    # Local import keeps i18n free of import-time deps on config/db.
    from .. import config
    try:
        return config.get_app_config("language")
    except Exception:
        return None


def _resolve_initial_language():
    env = os.environ.get("MISSKEY_CLI_LANG")
    if env and env in SUPPORTED_LANGS:
        return env

    stored = _load_stored_language()
    if stored and stored in SUPPORTED_LANGS:
        return stored

    lang = os.environ.get("LANG")
    if lang:
        prefix = lang[:2].lower()
        if prefix in SUPPORTED_LANGS:
            return prefix

    return DEFAULT_LANG


def init_language():
    """One-shot initialization called from main.main()."""
    _apply_language(_resolve_initial_language())


def set_language(code):
    """Persist + apply the chosen language. Raises ValueError on unknown."""
    if code not in SUPPORTED_LANGS:
        raise ValueError(code)
    from .. import config
    config.set_app_config("language", code)
    _apply_language(code)
