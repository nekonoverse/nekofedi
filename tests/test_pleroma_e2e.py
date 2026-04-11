"""E2E tests for the Pleroma code path (react() via Pleroma extension).

Pleroma supports emoji reactions through
``PUT /api/v1/pleroma/statuses/:id/reactions/:emoji``, which is what our
``MastodonClient`` dispatches to when ``software`` is ``pleroma``, ``akkoma``
or ``fedibird``. This suite exercises that endpoint against a real Pleroma
instance (plain HTTP, single user, no federation).
"""

import os
import time

import pytest
import requests

from misskey_cli.api import (
    MASTODON_OOB_REDIRECT,
    MASTODON_SCOPES,
    MastodonClient,
    detect_software,
)

PLEROMA_HOST = os.environ.get("PLEROMA_HOST", "pleroma:4000")
BASE = f"http://{PLEROMA_HOST}"


def _create_app():
    resp = requests.post(
        f"{BASE}/api/v1/apps",
        json={
            "client_name": "misskey-cli-e2e",
            "redirect_uris": MASTODON_OOB_REDIRECT,
            "scopes": MASTODON_SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _obtain_token(username, password):
    app = _create_app()
    resp = requests.post(
        f"{BASE}/oauth/token",
        data={
            "client_id": app["client_id"],
            "client_secret": app["client_secret"],
            "grant_type": "password",
            "username": username,
            "password": password,
            "scope": MASTODON_SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def bob_token():
    return _obtain_token("bob", "Password1234!")


@pytest.fixture(scope="session")
def bob(bob_token):
    return MastodonClient(
        host=PLEROMA_HOST, token=bob_token, scheme="http", software="pleroma"
    )


# ---------- detect_software against a real Pleroma instance ----------


def test_detect_software_reports_pleroma():
    software = detect_software(PLEROMA_HOST, scheme="http")
    assert software == "pleroma"


# ---------- Profile / timeline / note basics ----------


def test_i(bob):
    me = bob.i()
    assert me["username"] == "bob"


def test_create_note_public(bob):
    result = bob.create_note("pleroma E2E public note")
    note = result["createdNote"]
    assert note["text"] == "pleroma E2E public note"
    assert note["visibility"] == "public"
    assert note["id"]


def test_create_note_home_visibility_roundtrip(bob):
    """home (Misskey) → unlisted (Pleroma) → home after normalization."""
    result = bob.create_note("pleroma home visibility", visibility="home")
    note = result["createdNote"]
    assert note["visibility"] == "home"


def test_show_note(bob):
    created = bob.create_note("pleroma show_note target")["createdNote"]
    fetched = bob.show_note(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["text"] == "pleroma show_note target"


def test_timeline_local_contains_recent_post(bob):
    bob.create_note("pleroma local timeline marker")
    time.sleep(1)
    notes = bob.timeline("local", limit=10)
    assert isinstance(notes, list)
    assert any(n.get("text") == "pleroma local timeline marker" for n in notes)


def test_timeline_global_returns_list(bob):
    notes = bob.timeline("global", limit=5)
    assert isinstance(notes, list)


# ---------- React via Pleroma endpoint ----------


def test_react_with_unicode_emoji(bob):
    """Pleroma supports emoji reactions natively — result must NOT be None."""
    note = bob.create_note("pleroma react unicode target")["createdNote"]
    result = bob.react(note["id"], ":\u2b50:")
    # On Pleroma the PUT endpoint returns the updated status, so result is a dict.
    assert result is not None


def test_react_unicode_appears_on_status(bob):
    """After reacting, the reaction should show up in the status's reactions."""
    note = bob.create_note("pleroma react reflected target")["createdNote"]
    bob.react(note["id"], ":\U0001f389:")  # 🎉
    time.sleep(1)
    fetched = bob.show_note(note["id"])
    assert fetched.get("reactions"), "expected non-empty reactions map"
    # The emoji key may be the bare unicode or the shortcode depending on
    # Pleroma version; both are acceptable as long as the counter is ≥ 1.
    assert any(v >= 1 for v in fetched["reactions"].values())


# ---------- Notifications ----------


def test_notifications_list(bob):
    notifs = bob.notifications(limit=5)
    assert isinstance(notifs, list)


def test_emojis_returns_list(bob):
    emojis = bob.emojis()
    assert isinstance(emojis, list)


# ---------- Lists / list timeline ----------


def test_lists_returns_normalized_name(bob, bob_token, ensure_mastodon_list):
    ensure_mastodon_list(BASE, bob_token, "pleroma-e2e-list")
    lists = bob.lists()
    assert isinstance(lists, list)
    names = [lst.get("name") for lst in lists]
    assert "pleroma-e2e-list" in names
    for lst in lists:
        assert lst.get("id")
        assert "name" in lst


def test_list_timeline_returns_list(bob, bob_token, ensure_mastodon_list):
    list_id = ensure_mastodon_list(BASE, bob_token, "pleroma-e2e-list-tl")
    notes = bob.timeline("list", limit=5, list_id=list_id)
    assert isinstance(notes, list)


def test_list_timeline_without_list_id_raises(bob):
    with pytest.raises(ValueError):
        bob.timeline("list", limit=5)
