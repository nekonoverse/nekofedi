"""Unit tests for the i18n layer (no network, no docker stack)."""
import importlib

import pytest


@pytest.fixture
def i18n_fresh(monkeypatch, tmp_path):
    """Force an isolated config dir + clear env, then return a fresh i18n module.

    Each test calling this fixture gets its own SQLite DB so DB-resolution
    tests don't bleed into each other.
    """
    monkeypatch.setenv("MISSKEY_CLI_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("MISSKEY_CLI_LANG", raising=False)
    monkeypatch.delenv("LANG", raising=False)

    # Reset the relevant modules so the patched env is observed and the
    # config singleton points at our temp dir.
    import misskey_cli.config
    import misskey_cli.db
    import misskey_cli.i18n
    importlib.reload(misskey_cli.config)
    importlib.reload(misskey_cli.db)
    importlib.reload(misskey_cli.i18n)

    # Run migrations so app_config exists in this temp DB.
    from misskey_cli.migrate import run_upgrade
    run_upgrade()

    return misskey_cli.i18n


# ---------- Catalog completeness ----------


def test_catalog_keys_match_across_languages():
    from misskey_cli.i18n import _CATALOGS

    en_keys = set(_CATALOGS["en"].keys())
    ja_keys = set(_CATALOGS["ja"].keys())
    fr_keys = set(_CATALOGS["fr"].keys())

    assert en_keys == ja_keys, f"ja missing: {en_keys - ja_keys}, ja extra: {ja_keys - en_keys}"
    assert en_keys == fr_keys, f"fr missing: {en_keys - fr_keys}, fr extra: {fr_keys - en_keys}"


def test_catalog_placeholders_match_across_languages():
    """Every {placeholder} in en must also exist in ja and fr for the same key."""
    import re

    from misskey_cli.i18n import _CATALOGS

    placeholder_re = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    for key, en_template in _CATALOGS["en"].items():
        en_placeholders = set(placeholder_re.findall(en_template))
        for lang in ("ja", "fr"):
            other = _CATALOGS[lang][key]
            other_placeholders = set(placeholder_re.findall(other))
            assert en_placeholders == other_placeholders, (
                f"placeholder mismatch for {key!r} in {lang}: "
                f"en={en_placeholders} {lang}={other_placeholders}"
            )


# ---------- Lookup with kwargs ----------


def test_lookup_formats_kwargs_in_each_language(i18n_fresh):
    i18n = i18n_fresh

    for code in i18n.SUPPORTED_LANGS:
        i18n._apply_language(code)
        result = i18n._("status.posted", id="abc", visibility="public")
        assert "abc" in result
        assert "public" in result


def test_missing_key_returns_key_itself(i18n_fresh):
    i18n = i18n_fresh
    i18n._apply_language("en")
    assert i18n._("definitely.no.such.key") == "definitely.no.such.key"


def test_missing_key_with_kwargs_does_not_crash(i18n_fresh):
    i18n = i18n_fresh
    i18n._apply_language("ja")
    # Key has no {message} placeholder, so format() may KeyError → return raw template
    assert i18n._("definitely.no.such.key", message="boom") == "definitely.no.such.key"


def test_missing_key_in_one_language_falls_back_to_en(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    # Inject a synthetic key into the en catalog only and verify ja fall back.
    i18n._CATALOGS["en"]["test.fallback_only_in_en"] = "english fallback {who}"
    try:
        i18n._apply_language("ja")
        assert i18n._("test.fallback_only_in_en", who="bob") == "english fallback bob"
    finally:
        del i18n._CATALOGS["en"]["test.fallback_only_in_en"]


# ---------- Resolution priority (env > db > LANG > default) ----------


def test_resolve_default_when_nothing_set(i18n_fresh):
    i18n = i18n_fresh
    assert i18n._resolve_initial_language() == "en"


def test_resolve_lang_env_only(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n._resolve_initial_language() == "ja"


def test_resolve_lang_env_unsupported_falls_back(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    monkeypatch.setenv("LANG", "C.UTF-8")
    assert i18n._resolve_initial_language() == "en"


def test_resolve_db_beats_lang(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    from misskey_cli import config
    config.set_app_config("language", "fr")
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n._resolve_initial_language() == "fr"


def test_resolve_env_beats_db_and_lang(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    from misskey_cli import config
    config.set_app_config("language", "ja")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("MISSKEY_CLI_LANG", "fr")
    assert i18n._resolve_initial_language() == "fr"


def test_resolve_unsupported_env_is_ignored(i18n_fresh, monkeypatch):
    i18n = i18n_fresh
    monkeypatch.setenv("MISSKEY_CLI_LANG", "de")
    monkeypatch.setenv("LANG", "ja_JP.UTF-8")
    assert i18n._resolve_initial_language() == "ja"


# ---------- set_language persistence ----------


def test_set_language_persists_and_applies(i18n_fresh):
    i18n = i18n_fresh
    from misskey_cli import config

    i18n.set_language("fr")
    assert i18n.get_language() == "fr"
    assert config.get_app_config("language") == "fr"

    i18n.set_language("ja")
    assert i18n.get_language() == "ja"
    assert config.get_app_config("language") == "ja"


def test_set_language_rejects_unknown(i18n_fresh):
    i18n = i18n_fresh
    with pytest.raises(ValueError):
        i18n.set_language("de")
