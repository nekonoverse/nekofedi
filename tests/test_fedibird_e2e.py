"""E2E tests for the Fedibird code path.

Fedibird is a Mastodon fork with its own emoji-reaction API
(``PUT /api/v1/statuses/:id/emoji_reactions/:emoji``) — distinct from the
Pleroma extension path, which Fedibird does NOT expose. This suite exercises
that endpoint end-to-end against a real Fedibird build, and checks that
``detect_software`` recognises a Fedibird instance even when it self-reports
``software.name == "mastodon"`` in nodeinfo (the common case: Fedibird leaks
the ``fedibird`` substring in ``software.version``).

Fedibird also:
  - Reinterprets ``local=true`` on the public timeline as "local-only
    visibility" and uses ``remote=false`` for the usual local timeline.
  - Disables OAuth ``grant_type=password``, so the test token is minted
    in-DB by ``fedibird-entrypoint.sh`` (via
    ``Doorkeeper::AccessToken.find_or_create_for``) and passed in through
    the ``FEDIBIRD_TOKEN`` environment variable.
"""

import os
import time

import pytest

from misskey_cli.api import MastodonClient, detect_software

FEDIBIRD_HOST = os.environ.get("FEDIBIRD_HOST", "web:3000")
FEDIBIRD_TOKEN = os.environ.get("FEDIBIRD_TOKEN", "")
BASE = f"http://{FEDIBIRD_HOST}"


@pytest.fixture(scope="session")
def bob_token():
    if not FEDIBIRD_TOKEN:
        pytest.skip("FEDIBIRD_TOKEN env var not set")
    return FEDIBIRD_TOKEN


@pytest.fixture(scope="session")
def bob(bob_token):
    return MastodonClient(
        host=FEDIBIRD_HOST, token=bob_token, scheme="http", software="fedibird"
    )


# ---------- detect_software against a real Fedibird instance ----------


def test_detect_software_reports_fedibird():
    software = detect_software(FEDIBIRD_HOST, scheme="http")
    assert software == "fedibird"


# ---------- Profile / timeline / note basics ----------


def test_i(bob):
    me = bob.i()
    assert me["username"] == "bob"


def test_create_note_public(bob):
    result = bob.create_note("fedibird E2E public note")
    note = result["createdNote"]
    assert note["text"] == "fedibird E2E public note"
    assert note["visibility"] == "public"
    assert note["id"]


def test_show_note(bob):
    created = bob.create_note("fedibird show_note target")["createdNote"]
    fetched = bob.show_note(created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["text"] == "fedibird show_note target"


def test_timeline_local_contains_recent_post(bob):
    bob.create_note("fedibird local timeline marker")
    time.sleep(1)
    notes = bob.timeline("local", limit=10)
    assert isinstance(notes, list)
    assert any(n.get("text") == "fedibird local timeline marker" for n in notes)


# ---------- React via Pleroma extension endpoint ----------


def test_react_with_unicode_emoji(bob):
    """Fedibird supports Pleroma-style emoji reactions — result must NOT be None."""
    note = bob.create_note("fedibird react unicode target")["createdNote"]
    result = bob.react(note["id"], ":\u2b50:")
    assert result is not None


def test_react_unicode_appears_on_status(bob):
    note = bob.create_note("fedibird react reflected target")["createdNote"]
    bob.react(note["id"], ":\U0001f389:")  # 🎉
    time.sleep(1)
    fetched = bob.show_note(note["id"])
    assert fetched.get("reactions"), "expected non-empty reactions map"
    assert any(v >= 1 for v in fetched["reactions"].values())


def test_notifications_list(bob):
    notifs = bob.notifications(limit=5)
    assert isinstance(notifs, list)


def test_emojis_returns_list(bob):
    emojis = bob.emojis()
    assert isinstance(emojis, list)


# ---------- Lists / list timeline ----------


def test_lists_returns_normalized_name(bob, bob_token, ensure_mastodon_list):
    ensure_mastodon_list(BASE, bob_token, "fedibird-e2e-list")
    lists = bob.lists()
    assert isinstance(lists, list)
    names = [lst.get("name") for lst in lists]
    assert "fedibird-e2e-list" in names
    for lst in lists:
        assert lst.get("id")
        assert "name" in lst


def test_list_timeline_returns_list(bob, bob_token, ensure_mastodon_list):
    list_id = ensure_mastodon_list(BASE, bob_token, "fedibird-e2e-list-tl")
    notes = bob.timeline("list", limit=5, list_id=list_id)
    assert isinstance(notes, list)


def test_list_timeline_without_list_id_raises(bob):
    with pytest.raises(ValueError):
        bob.timeline("list", limit=5)
