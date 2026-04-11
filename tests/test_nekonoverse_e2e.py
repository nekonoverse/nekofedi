import os
import re
import time

import pytest
import requests

from misskey_cli.api import (
    NEKONOVERSE_OOB_REDIRECT,
    NEKONOVERSE_SCOPES,
    NekonoverseClient,
)

NEKONOVERSE_HOST = os.environ.get("NEKONOVERSE_HOST", "app:8000")
BASE = f"http://{NEKONOVERSE_HOST}"

OOB_CODE_RE = re.compile(r'<div id="oob-code"[^>]*>([^<]+)</div>')


def _register_user(username, password):
    """Register a user via the public registration endpoint.

    Returns the user response. Treats 201 as success and ignores 422
    "username already taken" so that re-runs against a stale DB still pass.
    """
    resp = requests.post(
        f"{BASE}/api/v1/accounts",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "display_name": username.capitalize(),
        },
        timeout=30,
    )
    if resp.status_code == 201:
        return resp.json()
    if resp.status_code == 422 and "taken" in resp.text.lower():
        return None
    resp.raise_for_status()


def _obtain_token(username, password):
    """Run the OAuth OOB flow non-interactively to get an access token."""
    # Step 1: register an OAuth app.
    app_resp = requests.post(
        f"{BASE}/api/v1/apps",
        json={
            "client_name": "misskey-cli-e2e",
            "redirect_uris": NEKONOVERSE_OOB_REDIRECT,
            "scopes": NEKONOVERSE_SCOPES,
        },
        timeout=30,
    )
    app_resp.raise_for_status()
    app = app_resp.json()
    client_id = app["client_id"]
    client_secret = app["client_secret"]

    # Step 2: submit the login form to /oauth/authorize. With both username
    # and password present the server treats this as a login submission and
    # issues an authorization code without requiring CSRF.
    auth_resp = requests.post(
        f"{BASE}/oauth/authorize",
        data={
            "client_id": client_id,
            "redirect_uri": NEKONOVERSE_OOB_REDIRECT,
            "scope": NEKONOVERSE_SCOPES,
            "response_type": "code",
            "username": username,
            "password": password,
        },
        timeout=30,
        allow_redirects=False,
    )
    auth_resp.raise_for_status()
    match = OOB_CODE_RE.search(auth_resp.text)
    assert match, f"OOB code not found in response: {auth_resp.text[:500]}"
    code = match.group(1).strip()

    # Step 3: exchange the code for an access token.
    token_resp = requests.post(
        f"{BASE}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": NEKONOVERSE_OOB_REDIRECT,
            "scope": NEKONOVERSE_SCOPES,
        },
        timeout=30,
    )
    token_resp.raise_for_status()
    return token_resp.json()["access_token"]


@pytest.fixture(scope="session")
def alice_token():
    _register_user("alice", "alice-password-1234")
    return _obtain_token("alice", "alice-password-1234")


@pytest.fixture(scope="session")
def bob_token():
    _register_user("bob", "bob-password-1234")
    return _obtain_token("bob", "bob-password-1234")


@pytest.fixture(scope="session")
def alice(alice_token):
    return NekonoverseClient(host=NEKONOVERSE_HOST, token=alice_token, scheme="http")


@pytest.fixture(scope="session")
def bob(bob_token):
    return NekonoverseClient(host=NEKONOVERSE_HOST, token=bob_token, scheme="http")


def test_i(alice):
    me = alice.i()
    assert me["username"] == "alice"
    assert "notesCount" in me
    assert "followersCount" in me


def test_create_note_public(alice):
    result = alice.create_note("E2E public note")
    note = result["createdNote"]
    assert note["text"] == "E2E public note"
    assert note["visibility"] == "public"
    assert note["id"]


def test_create_note_home_visibility_roundtrip(alice):
    """home (Misskey) → unlisted (Mastodon) → home (back through normalization)."""
    result = alice.create_note("home visibility note", visibility="home")
    note = result["createdNote"]
    assert note["visibility"] == "home"


def test_create_note_with_cw(alice):
    result = alice.create_note("spoiler body", cw="CW header")
    note = result["createdNote"]
    assert note["cw"] == "CW header"
    assert note["text"] == "spoiler body"


def test_show_note(alice):
    created = alice.create_note("show_note target")["createdNote"]
    fetched = alice.show_note(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["text"] == "show_note target"


def test_timeline_local_contains_recent_post(alice):
    alice.create_note("local timeline marker")
    time.sleep(1)
    notes = alice.timeline("local", limit=10)
    assert isinstance(notes, list)
    assert any(n.get("text") == "local timeline marker" for n in notes)


def test_timeline_home_returns_list(alice):
    notes = alice.timeline("home", limit=5)
    assert isinstance(notes, list)


def test_timeline_global_returns_list(alice):
    notes = alice.timeline("global", limit=5)
    assert isinstance(notes, list)


def test_reply_and_renote(alice, bob):
    parent = alice.create_note("parent note for reply test")["createdNote"]

    reply = bob.create_note(
        "@alice replying from bob",
        reply_id=parent["id"],
    )["createdNote"]
    assert reply["id"]

    renote = bob.renote(parent["id"])
    assert renote and renote.get("id")


def test_react_unicode(alice, bob):
    note = alice.create_note("react target")["createdNote"]
    # Wrapped in colons to match what cli.cmd_react passes through.
    bob.react(note["id"], ":\u2b50:")


def test_react_custom_shortcode(alice, bob):
    """Custom emoji shortcodes must be sent colon-wrapped to pass server-side
    validation. The shortcode does not need to exist as a registered emoji —
    add_reaction stores the bare string and only enriches federation tags when
    a row exists, so this is a pure validator regression test."""
    note = alice.create_note("react custom target")["createdNote"]
    bob.react(note["id"], ":testreact:")


def test_notifications_list(bob):
    notifs = bob.notifications(limit=5)
    assert isinstance(notifs, list)


def test_emojis_returns_list(alice):
    emojis = alice.emojis()
    assert isinstance(emojis, list)
    # Fresh instance has no custom emojis; the contract is that we return a list.


# ---------- Lists / list timeline ----------


def test_lists_returns_normalized_name(bob, bob_token, ensure_mastodon_list):
    ensure_mastodon_list(BASE, bob_token, "nekonoverse-e2e-list")
    lists = bob.lists()
    assert isinstance(lists, list)
    names = [lst.get("name") for lst in lists]
    assert "nekonoverse-e2e-list" in names
    for lst in lists:
        assert lst.get("id")
        assert "name" in lst


def test_list_timeline_returns_list(bob, bob_token, ensure_mastodon_list):
    list_id = ensure_mastodon_list(BASE, bob_token, "nekonoverse-e2e-list-tl")
    notes = bob.timeline("list", limit=5, list_id=list_id)
    assert isinstance(notes, list)


def test_list_timeline_without_list_id_raises(bob):
    with pytest.raises(ValueError):
        bob.timeline("list", limit=5)
