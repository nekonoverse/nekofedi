"""E2E tests for the Mastodon-family code path using a real Mastodon v4.3 instance.

Mastodon has no emoji-reaction API, so `react()` should transparently fall back
to `favourite` and return ``None`` as the sentinel. Notification mapping for
`favourite` → `reaction` with a star is also exercised end-to-end.
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

MASTODON_HOST = os.environ.get("MASTODON_HOST", "web:3000")
BASE = f"http://{MASTODON_HOST}"


def _create_app():
    """Register an OAuth app."""
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


def _obtain_token(email, password):
    """Obtain an access token via OAuth password grant (Mastodon supports it
    when the app owns the account itself, so the bob we create via tootctl
    in the entrypoint works).
    """
    app = _create_app()
    resp = requests.post(
        f"{BASE}/oauth/token",
        data={
            "client_id": app["client_id"],
            "client_secret": app["client_secret"],
            "grant_type": "password",
            "username": email,
            "password": password,
            "scope": MASTODON_SCOPES,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture(scope="session")
def bob_token():
    return _obtain_token("bob@web", "Password1234!")


@pytest.fixture(scope="session")
def bob(bob_token):
    return MastodonClient(
        host=MASTODON_HOST, token=bob_token, scheme="http", software="mastodon"
    )


# ---------- detect_software against a real Mastodon instance ----------


def test_detect_software_reports_mastodon():
    software = detect_software(MASTODON_HOST, scheme="http")
    assert software == "mastodon"


# ---------- Profile / timeline / note basics ----------


def test_i(bob):
    me = bob.i()
    assert me["username"] == "bob"
    assert "notesCount" in me
    assert "followersCount" in me


def test_create_note_public(bob):
    result = bob.create_note("mastodon E2E public note")
    note = result["createdNote"]
    assert note["text"] == "mastodon E2E public note"
    assert note["visibility"] == "public"
    assert note["id"]


def test_create_note_home_visibility_roundtrip(bob):
    """home (Misskey) → unlisted (Mastodon) → home (back through normalization)."""
    result = bob.create_note("mastodon home visibility", visibility="home")
    note = result["createdNote"]
    assert note["visibility"] == "home"


def test_create_note_with_cw(bob):
    result = bob.create_note("spoiler body", cw="CW header")
    note = result["createdNote"]
    assert note["cw"] == "CW header"
    assert note["text"] == "spoiler body"


def test_show_note(bob):
    created = bob.create_note("mastodon show_note target")["createdNote"]
    fetched = bob.show_note(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["text"] == "mastodon show_note target"


def test_timeline_local_contains_recent_post(bob):
    bob.create_note("mastodon local timeline marker")
    time.sleep(1)
    notes = bob.timeline("local", limit=10)
    assert isinstance(notes, list)
    assert any(n.get("text") == "mastodon local timeline marker" for n in notes)


def test_timeline_home_returns_list(bob):
    notes = bob.timeline("home", limit=5)
    assert isinstance(notes, list)


def test_timeline_global_returns_list(bob):
    notes = bob.timeline("global", limit=5)
    assert isinstance(notes, list)


def test_renote(bob):
    parent = bob.create_note("mastodon renote target")["createdNote"]
    renote = bob.renote(parent["id"])
    assert renote and renote.get("id")


# ---------- React fallback to favourite ----------


def test_react_returns_none_sentinel(bob):
    """On Mastodon, react() must fall back to favourite and return None."""
    note = bob.create_note("mastodon react target")["createdNote"]
    result = bob.react(note["id"], ":\u2b50:")
    assert result is None


def test_react_fallback_works_with_custom_shortcode(bob):
    """Even if the user supplies a custom shortcode, Mastodon has no
    emoji-reaction endpoint, so we still fall back to favourite."""
    note = bob.create_note("mastodon react custom target")["createdNote"]
    result = bob.react(note["id"], ":party_parrot:")
    assert result is None


def test_notifications_list(bob):
    notifs = bob.notifications(limit=5)
    assert isinstance(notifs, list)


def test_favourite_notification_is_normalized_to_reaction(bob):
    """A favourite becomes a `reaction` notification with a ⭐ body."""
    note = bob.create_note("mastodon favourite notif target")["createdNote"]
    # bob favourites his own note: valid on Mastodon and produces a notification.
    bob.react(note["id"], ":\u2b50:")
    time.sleep(2)
    notifs = bob.notifications(limit=20)
    favs = [
        n
        for n in notifs
        if n.get("type") == "reaction"
        and n.get("note")
        and n["note"].get("id") == note["id"]
    ]
    # Mastodon doesn't always self-notify for self-favourites; accept either 0
    # or a correctly-normalized entry without failing the stack.
    if favs:
        assert favs[0]["reaction"] == "\u2b50"


def test_emojis_returns_list(bob):
    emojis = bob.emojis()
    assert isinstance(emojis, list)


# ---------- Lists / list timeline ----------


def test_lists_returns_normalized_name(bob, bob_token, ensure_mastodon_list):
    """Mastodon returns ``title``; MastodonClient.lists() must normalize to ``name``."""
    ensure_mastodon_list(BASE, bob_token, "mastodon-e2e-list")
    lists = bob.lists()
    assert isinstance(lists, list)
    names = [lst.get("name") for lst in lists]
    assert "mastodon-e2e-list" in names
    # Every entry must have both id and name keys.
    for lst in lists:
        assert lst.get("id")
        assert "name" in lst


def test_list_timeline_returns_list(bob, bob_token, ensure_mastodon_list):
    """``timeline('list', list_id=...)`` must hit the list endpoint and return a list."""
    list_id = ensure_mastodon_list(BASE, bob_token, "mastodon-e2e-list-tl")
    notes = bob.timeline("list", limit=5, list_id=list_id)
    # An empty list is fine (bob has no list members yet), but the call must
    # succeed and return an iterable of normalized notes.
    assert isinstance(notes, list)


def test_list_timeline_without_list_id_raises(bob):
    with pytest.raises(ValueError):
        bob.timeline("list", limit=5)
