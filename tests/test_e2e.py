import os
import time

import pytest
import requests

from misskey_cli.api import MisskeyClient

MISSKEY_HOST = os.environ.get("MISSKEY_HOST", "localhost:61812")
SETUP_PASSWORD = "test_setup_password"


@pytest.fixture(scope="session")
def admin_token():
    """Create admin user and return token."""
    resp = requests.post(
        f"http://{MISSKEY_HOST}/api/admin/accounts/create",
        json={
            "username": "admin",
            "password": "adminpassword",
            "setupPassword": SETUP_PASSWORD,
        },
        timeout=30,
    )
    if resp.status_code == 200:
        data = resp.json()
        assert "token" in data
        return data["token"]
    # Admin already exists, sign in via signin-flow
    resp = requests.post(
        f"http://{MISSKEY_HOST}/api/signin-flow",
        json={"username": "admin", "password": "adminpassword"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    assert "finished" in data
    return data["i"]


@pytest.fixture(scope="session")
def client(admin_token):
    """Return MisskeyClient authenticated as admin."""
    return MisskeyClient(host=MISSKEY_HOST, token=admin_token, scheme="http")


def test_i(client):
    me = client.i()
    assert me["username"] == "admin"


def test_create_note(client):
    result = client.create_note("E2E test note")
    note = result["createdNote"]
    assert note["text"] == "E2E test note"
    assert note["visibility"] == "public"


def test_create_note_with_visibility(client):
    result = client.create_note("home visibility note", visibility="home")
    note = result["createdNote"]
    assert note["visibility"] == "home"


def test_create_note_with_cw(client):
    result = client.create_note("spoiler content", cw="CW test")
    note = result["createdNote"]
    assert note["cw"] == "CW test"
    assert note["text"] == "spoiler content"


def test_timeline_local(client):
    client.create_note("timeline test note")
    time.sleep(1)
    notes = client.timeline("local", limit=5)
    assert len(notes) > 0
    texts = [n.get("text") for n in notes]
    assert "timeline test note" in texts


def test_timeline_home(client):
    notes = client.timeline("home", limit=5)
    assert isinstance(notes, list)


def test_reply(client):
    parent = client.create_note("parent note")["createdNote"]
    result = client.create_note("reply text", reply_id=parent["id"])
    reply = result["createdNote"]
    assert reply["replyId"] == parent["id"]
    assert reply["text"] == "reply text"


def test_renote(client):
    original = client.create_note("renote target")["createdNote"]
    result = client.renote(original["id"])
    renote = result["createdNote"]
    assert renote["renoteId"] == original["id"]


def test_react(client):
    note = client.create_note("react target")["createdNote"]
    client.react(note["id"], "\u2764\ufe0f")


def test_notifications(client):
    notifs = client.notifications(limit=5)
    assert isinstance(notifs, list)


# ---------- Lists / list timeline ----------


def _ensure_list(client, name):
    """Create a user list (or return the existing one) and return its id."""
    existing = client._post("users/lists/list") or []
    for lst in existing:
        if lst.get("name") == name:
            return lst["id"]
    created = client._post("users/lists/create", name=name)
    return created["id"]


def test_lists_returns_id_name_pairs(client):
    _ensure_list(client, "misskey-e2e-list")
    lists = client.lists()
    assert isinstance(lists, list)
    names = [lst.get("name") for lst in lists]
    assert "misskey-e2e-list" in names
    for lst in lists:
        assert lst.get("id")
        assert "name" in lst


def test_list_timeline_returns_list(client):
    list_id = _ensure_list(client, "misskey-e2e-list-tl")
    notes = client.timeline("list", limit=5, list_id=list_id)
    # Misskey returns the raw array; an empty list is OK (no members yet).
    assert isinstance(notes, list)


def test_list_timeline_without_list_id_raises(client):
    with pytest.raises(ValueError):
        client.timeline("list", limit=5)
