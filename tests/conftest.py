"""Shared E2E test fixtures.

pytest automatically imports ``conftest.py`` for every test in the directory,
so fixtures defined here are available to all E2E suites without per-file
imports. Keep this file focused on cross-suite helpers — suite-specific
fixtures belong in their respective test modules.
"""

import pytest
import requests


@pytest.fixture
def ensure_mastodon_list():
    """Return a helper that creates (or reuses) a Mastodon-compatible list.

    Used by the Mastodon, Fedibird, Pleroma, Akkoma and Nekonoverse E2E
    suites, all of which speak the Mastodon client API
    (``POST /api/v1/lists`` with ``{"title": ...}``). Re-runs against a dirty
    DB are handled by looking up an existing entry with the same title first.

    Usage::

        def test_foo(ensure_mastodon_list, bob_token):
            list_id = ensure_mastodon_list(BASE, bob_token, "some-title")
    """

    def _create(base, token, title):
        headers = {"Authorization": f"Bearer {token}"}
        existing = requests.get(f"{base}/api/v1/lists", headers=headers, timeout=30)
        existing.raise_for_status()
        for lst in existing.json() or []:
            if lst.get("title") == title:
                return lst["id"]
        resp = requests.post(
            f"{base}/api/v1/lists",
            headers=headers,
            json={"title": title},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    return _create
