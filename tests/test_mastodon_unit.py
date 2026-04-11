"""Unit tests for MastodonClient / detect_software (no network, no docker)."""
import io
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.document import Document

from misskey_cli.api import (
    MASTODON_SOFTWARE,
    MastodonClient,
    MisskeyClient,
    NekonoverseClient,
    detect_software,
    make_client,
)
from misskey_cli.cli import ALIASES, COMMANDS, MisskeyCompleter


# ---------- MASTODON_SOFTWARE set ----------


def test_mastodon_family_includes_all_supported_servers():
    assert "mastodon" in MASTODON_SOFTWARE
    assert "fedibird" in MASTODON_SOFTWARE
    assert "pleroma" in MASTODON_SOFTWARE
    assert "akkoma" in MASTODON_SOFTWARE
    assert "gotosocial" in MASTODON_SOFTWARE
    assert "hometown" in MASTODON_SOFTWARE
    assert "nekonoverse" in MASTODON_SOFTWARE


def test_nekonoverse_client_is_alias_of_mastodon_client():
    """Legacy imports of NekonoverseClient must keep working."""
    assert NekonoverseClient is MastodonClient


# ---------- _unwrap_emoji ----------


class TestUnwrapEmoji:
    def test_shortcode_is_preserved(self):
        assert MastodonClient._unwrap_emoji(":foo:") == ":foo:"

    def test_remote_shortcode_is_preserved(self):
        assert MastodonClient._unwrap_emoji(":foo@bar.example:") == ":foo@bar.example:"

    def test_shortcode_with_digits(self):
        assert MastodonClient._unwrap_emoji(":foo_1:") == ":foo_1:"

    def test_unicode_emoji_wrapped_in_colons_is_unwrapped(self):
        assert MastodonClient._unwrap_emoji(":⭐:") == "⭐"

    def test_multichar_unicode_is_unwrapped(self):
        # Heart emoji wrapped by the CLI.
        assert MastodonClient._unwrap_emoji(":❤️:") == "❤️"

    def test_bare_unicode_without_colons_passes_through(self):
        assert MastodonClient._unwrap_emoji("⭐") == "⭐"

    def test_bare_shortcode_without_colons_passes_through(self):
        # The CLI wraps in colons before calling react(), but be robust.
        assert MastodonClient._unwrap_emoji("foo") == "foo"


# ---------- react() dispatch ----------


def _client(software):
    return MastodonClient(host="x", token="t", scheme="http", software=software)


class TestReactDispatch:
    @pytest.mark.parametrize("software", ["pleroma", "akkoma"])
    def test_pleroma_family_uses_put_pleroma_endpoint(self, software):
        c = _client(software)
        with patch("misskey_cli.api.requests.put") as put:
            put.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            result = c.react("note123", ":foo:")
            put.assert_called_once()
            url = put.call_args[0][0]
            assert url == f"http://x/api/v1/pleroma/statuses/note123/reactions/%3Afoo%3A"
            assert result == {}

    @pytest.mark.parametrize("software", ["pleroma", "akkoma"])
    def test_pleroma_family_unwraps_unicode_emoji(self, software):
        c = _client(software)
        with patch("misskey_cli.api.requests.put") as put:
            put.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            c.react("note1", ":⭐:")
            url = put.call_args[0][0]
            # ⭐ is urlencoded, no surrounding colons.
            assert "/reactions/%E2%AD%90" in url
            assert "%3A" not in url.split("/reactions/")[1]

    def test_fedibird_uses_put_emoji_reactions_endpoint(self):
        """Fedibird ships its own PUT /api/v1/statuses/:id/emoji_reactions/:emoji
        (distinct from the Pleroma extension path, which it does not expose)."""
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.put") as put:
            put.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            result = c.react("noteFB", ":foo:")
            put.assert_called_once()
            url = put.call_args[0][0]
            assert url == "http://x/api/v1/statuses/noteFB/emoji_reactions/%3Afoo%3A"
            assert result == {}

    def test_fedibird_unwraps_unicode_emoji(self):
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.put") as put:
            put.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            c.react("noteFB", ":⭐:")
            url = put.call_args[0][0]
            assert "/emoji_reactions/%E2%AD%90" in url
            assert "%3A" not in url.split("/emoji_reactions/")[1]

    def test_nekonoverse_uses_post_react_endpoint(self):
        c = _client("nekonoverse")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            c.react("noteN", ":foo:")
            url = post.call_args[0][0]
            assert url == "http://x/api/v1/statuses/noteN/react/%3Afoo%3A"

    @pytest.mark.parametrize("software", ["mastodon", "gotosocial", "hometown"])
    def test_mastodon_family_falls_back_to_favourite(self, software):
        c = _client(software)
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            result = c.react("noteM", ":foo:")
            # Exactly one call, to /favourite.
            post.assert_called_once()
            url = post.call_args[0][0]
            assert url == "http://x/api/v1/statuses/noteM/favourite"
            # Sentinel: None signals the fallback to the CLI.
            assert result is None

    def test_fallback_result_is_none_even_for_unicode_emoji(self):
        c = _client("mastodon")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(status_code=200, content=b"{}", json=lambda: {})
            assert c.react("note1", ":⭐:") is None


# ---------- _normalize_notif ----------


class TestNormalizeNotif:
    def _make(self, software="mastodon"):
        return _client(software)

    def test_favourite_maps_to_reaction_with_star(self):
        c = self._make()
        result = c._normalize_notif(
            {
                "type": "favourite",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "1", "username": "alice", "acct": "alice"},
                "status": None,
            }
        )
        assert result["type"] == "reaction"
        assert result["reaction"] == "⭐"

    def test_nekonoverse_reaction_with_shortcode(self):
        c = self._make("nekonoverse")
        result = c._normalize_notif(
            {
                "type": "reaction",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "1", "username": "alice", "acct": "alice"},
                "emoji": {"shortcode": "party_parrot"},
                "status": None,
            }
        )
        assert result["type"] == "reaction"
        assert result["reaction"] == ":party_parrot:"

    def test_pleroma_emoji_reaction_unicode(self):
        c = self._make("pleroma")
        result = c._normalize_notif(
            {
                "type": "pleroma:emoji_reaction",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "1", "username": "alice", "acct": "alice"},
                "emoji": "🎉",
                "status": None,
            }
        )
        assert result["type"] == "reaction"
        assert result["reaction"] == "🎉"

    def test_pleroma_emoji_reaction_custom_shortcode(self):
        c = self._make("pleroma")
        result = c._normalize_notif(
            {
                "type": "pleroma:emoji_reaction",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "1", "username": "alice", "acct": "alice"},
                "emoji": ":party_parrot:",
                "status": None,
            }
        )
        assert result["type"] == "reaction"
        assert result["reaction"] == ":party_parrot:"

    def test_reblog_maps_to_renote(self):
        c = self._make()
        result = c._normalize_notif(
            {
                "type": "reblog",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "1", "username": "alice", "acct": "alice"},
                "status": None,
            }
        )
        assert result["type"] == "renote"


# ---------- _normalize_note reactions ----------


class TestNormalizeReactions:
    def test_fedibird_emoji_reactions_field(self):
        c = _client("fedibird")
        note = c._normalize_note(
            {
                "id": "1",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "2", "username": "alice", "acct": "alice"},
                "content": "<p>hi</p>",
                "visibility": "public",
                "emoji_reactions": [
                    {"name": "🎉", "count": 3},
                    {"name": ":party:", "count": 1},
                ],
            }
        )
        assert note["reactions"] == {"🎉": 3, ":party:": 1}

    def test_pleroma_nested_emoji_reactions(self):
        c = _client("pleroma")
        note = c._normalize_note(
            {
                "id": "1",
                "created_at": "2024-01-01T00:00:00Z",
                "account": {"id": "2", "username": "alice", "acct": "alice"},
                "content": "<p>hi</p>",
                "visibility": "public",
                "pleroma": {
                    "emoji_reactions": [
                        {"name": "🎉", "count": 2},
                    ],
                },
            }
        )
        assert note["reactions"] == {"🎉": 2}


# ---------- detect_software Fedibird fallback ----------


def _mock_nodeinfo_chain(nodeinfo_doc, software_doc):
    """Helper that mocks both nodeinfo round-trips."""
    wellknown = MagicMock()
    wellknown.raise_for_status = MagicMock()
    wellknown.json = MagicMock(return_value=nodeinfo_doc)
    node = MagicMock()
    node.raise_for_status = MagicMock()
    node.json = MagicMock(return_value=software_doc)
    return wellknown, node


class TestDetectSoftware:
    def test_mastodon_vanilla(self):
        wellknown, node = _mock_nodeinfo_chain(
            {"links": [{"href": "https://example.com/nodeinfo/2.0"}]},
            {"software": {"name": "mastodon", "version": "4.3.0"}},
        )
        with patch("misskey_cli.api.requests.get", side_effect=[wellknown, node]):
            assert detect_software("example.com") == "mastodon"

    def test_fedibird_via_version_string(self):
        wellknown, node = _mock_nodeinfo_chain(
            {"links": [{"href": "https://fb.example/nodeinfo/2.0"}]},
            {"software": {"name": "mastodon", "version": "4.2.1+fedibird-20240420"}},
        )
        with patch("misskey_cli.api.requests.get", side_effect=[wellknown, node]):
            assert detect_software("fb.example") == "fedibird"

    def test_fedibird_via_repository_url(self):
        wellknown, node = _mock_nodeinfo_chain(
            {"links": [{"href": "https://fb.example/nodeinfo/2.0"}]},
            {
                "software": {
                    "name": "mastodon",
                    "version": "4.3.0",
                    "repository": "https://github.com/fedibird/mastodon",
                }
            },
        )
        with patch("misskey_cli.api.requests.get", side_effect=[wellknown, node]):
            assert detect_software("fb.example") == "fedibird"

    def test_pleroma(self):
        wellknown, node = _mock_nodeinfo_chain(
            {"links": [{"href": "https://pleroma.example/nodeinfo/2.1"}]},
            {"software": {"name": "pleroma", "version": "2.6.0"}},
        )
        with patch("misskey_cli.api.requests.get", side_effect=[wellknown, node]):
            assert detect_software("pleroma.example") == "pleroma"

    def test_misskey(self):
        wellknown, node = _mock_nodeinfo_chain(
            {"links": [{"href": "https://m.example/nodeinfo/2.1"}]},
            {"software": {"name": "misskey", "version": "2024.5.0"}},
        )
        with patch("misskey_cli.api.requests.get", side_effect=[wellknown, node]):
            assert detect_software("m.example") == "misskey"

    def test_network_failure_returns_none(self):
        import requests as _requests  # local alias — test-only
        with patch("misskey_cli.api.requests.get", side_effect=_requests.ConnectionError):
            assert detect_software("unreachable.example") is None


# ---------- timeline() per-software quirks ----------


class TestTimeline:
    @pytest.mark.parametrize("software", ["mastodon", "pleroma", "akkoma", "nekonoverse"])
    def test_local_uses_local_true(self, software):
        c = _client(software)
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(status_code=200, content=b"[]", json=lambda: [])
            c.timeline("local", limit=5)
            url = get.call_args[0][0]
            params = get.call_args.kwargs.get("params") or {}
            assert "/api/v1/timelines/public" in url
            assert params.get("local") == "true"
            assert "remote" not in params

    def test_fedibird_local_uses_remote_false(self):
        """Fedibird reinterprets ``local=true`` as "local-only visibility"
        and uses ``remote=false`` to mean "public timeline without remote posts"."""
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(status_code=200, content=b"[]", json=lambda: [])
            c.timeline("local", limit=5)
            params = get.call_args.kwargs.get("params") or {}
            assert params.get("remote") == "false"
            assert "local" not in params

    def test_fedibird_hybrid_uses_remote_false(self):
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(status_code=200, content=b"[]", json=lambda: [])
            c.timeline("hybrid", limit=5)
            params = get.call_args.kwargs.get("params") or {}
            assert params.get("remote") == "false"


# ---------- make_client routing ----------


class TestMakeClient:
    @pytest.mark.parametrize(
        "software", ["mastodon", "fedibird", "pleroma", "akkoma", "nekonoverse", "gotosocial", "hometown"],
    )
    def test_mastodon_family_routes_to_mastodon_client(self, software):
        c = make_client(host="x", token="t", software=software, scheme="http")
        assert isinstance(c, MastodonClient)
        assert c.software == software

    def test_misskey_routes_to_misskey_client(self):
        c = make_client(host="x", token="t", software="misskey", scheme="http")
        assert isinstance(c, MisskeyClient)


# ---------- lists() ----------


class TestMastodonLists:
    def test_normalizes_title_to_name(self):
        c = _client("mastodon")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {"id": "1", "title": "Friends"},
                    {"id": "2", "title": "Work"},
                ],
            )
            result = c.lists()
            get.assert_called_once()
            url = get.call_args[0][0]
            assert url == "http://x/api/v1/lists"
            assert result == [
                {"id": "1", "name": "Friends"},
                {"id": "2", "name": "Work"},
            ]

    def test_skips_entries_without_id(self):
        c = _client("mastodon")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {"title": "Orphan"},
                    {"id": "3", "title": "Keep"},
                ],
            )
            assert c.lists() == [{"id": "3", "name": "Keep"}]

    def test_empty_response(self):
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(
                status_code=200, content=b"[]", json=lambda: []
            )
            assert c.lists() == []


class TestMisskeyLists:
    def test_returns_id_name_pairs(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {"id": "abc", "name": "Close Friends"},
                    {"id": "def", "name": "News"},
                ],
            )
            result = c.lists()
            url = post.call_args[0][0]
            assert url == "http://m.example/api/users/lists/list"
            assert result == [
                {"id": "abc", "name": "Close Friends"},
                {"id": "def", "name": "News"},
            ]

    def test_skips_entries_without_id(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {"name": "Broken"},
                    {"id": "ok", "name": "Good"},
                ],
            )
            assert c.lists() == [{"id": "ok", "name": "Good"}]


# ---------- timeline('list') ----------


class TestListTimeline:
    def test_mastodon_list_timeline_hits_list_endpoint(self):
        c = _client("mastodon")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(
                status_code=200, content=b"[]", json=lambda: []
            )
            c.timeline("list", limit=5, list_id="list-1")
            url = get.call_args[0][0]
            assert url == "http://x/api/v1/timelines/list/list-1"
            params = get.call_args.kwargs.get("params") or {}
            assert params.get("limit") == 5

    @pytest.mark.parametrize(
        "software", ["mastodon", "fedibird", "pleroma", "akkoma", "nekonoverse"],
    )
    def test_mastodon_list_timeline_without_list_id_raises(self, software):
        c = _client(software)
        with pytest.raises(ValueError):
            c.timeline("list", limit=5)

    def test_fedibird_list_timeline_ignores_remote_override(self):
        """Fedibird's local/remote rewrite only applies to public TL, not list."""
        c = _client("fedibird")
        with patch("misskey_cli.api.requests.get") as get:
            get.return_value = MagicMock(
                status_code=200, content=b"[]", json=lambda: []
            )
            c.timeline("list", limit=5, list_id="fb-list")
            url = get.call_args[0][0]
            assert url == "http://x/api/v1/timelines/list/fb-list"
            params = get.call_args.kwargs.get("params") or {}
            assert "remote" not in params
            assert "local" not in params

    def test_misskey_list_timeline_posts_user_list_endpoint(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200, content=b"[]", json=lambda: []
            )
            c.timeline("list", limit=5, list_id="mk-list")
            url = post.call_args[0][0]
            assert url == "http://m.example/api/notes/user-list-timeline"
            body = post.call_args.kwargs.get("json") or {}
            assert body.get("listId") == "mk-list"
            assert body.get("limit") == 5

    def test_misskey_list_timeline_without_list_id_raises(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with pytest.raises(ValueError):
            c.timeline("list", limit=5)

    def test_misskey_unknown_timeline_type_raises(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with pytest.raises(ValueError):
            c.timeline("bogus", limit=5)


# ---------- CLI test helpers ----------


def _build_stub_cli(**stub_attrs):
    """Instantiate MisskeyCLI with the client and DB side-effects stubbed.

    Extra keyword arguments become ``stub.<name>.return_value = value``
    assignments on the mock client, so callers can override the default
    ``lists`` / ``timeline`` / ``create_note`` responses as needed.
    Returns ``(cli, stub)``.
    """
    from misskey_cli.cli import MisskeyCLI

    with patch("misskey_cli.cli.make_client") as mc, \
         patch("misskey_cli.config.CONFIG_DIR") as cd:
        cd.mkdir = MagicMock()
        stub = MagicMock()
        stub.logged_in = True
        stub.i.return_value = {"id": "u1", "username": "bob", "name": "Bob"}
        stub.timeline.return_value = []
        stub.lists.return_value = [
            {"id": "abc", "name": "friends"},
            {"id": "def", "name": "family"},
        ]
        stub.create_note.return_value = {
            "createdNote": {"id": "n1", "text": "hi", "visibility": "public"}
        }
        for attr, value in stub_attrs.items():
            getattr(stub, attr).return_value = value
        mc.return_value = stub
        cli = MisskeyCLI()
        return cli, stub


def _make_completer(*, emoji=None, note_meta=None, lists=None):
    """Build a :class:`MisskeyCompleter` with injected callbacks.

    Defaults:
      - ``emoji``: empty list
      - ``note_meta``: empty list
      - ``lists``: the canonical two-list fixture used across the file.
    """
    if lists is None:
        lists = [
            {"id": "abc", "name": "friends"},
            {"id": "def", "name": "family"},
        ]
    return MisskeyCompleter(
        get_emoji_names=lambda: emoji or [],
        get_note_meta=lambda: note_meta or [],
        get_lists=lambda: lists,
    )


def _complete_text(completer, text):
    """Return the list of completion texts a completer yields for ``text``."""
    doc = Document(text=text, cursor_position=len(text))
    return [c.text for c in completer.get_completions(doc, None)]


# ---------- CLI: tl list / default_timeline list completion and parsing ----------


class TestListCompleterAndCmds:
    """Covers the `tl list <target>` / `default_timeline list <target>` paths:

    - Tab completion at the ``<target>`` position offers list names
    - ``cmd_tl`` parses ``tl list <name>`` and resolves to an id
    - ``cmd_tl`` still accepts a bare limit (``tl list 5``) → active list
    - ``cmd_default_timeline list <target>`` switches the active list and
      sets the default in one shot
    """

    def test_tl_list_offers_list_names(self):
        with patch("misskey_cli.config.get_active_list_id", return_value=None):
            results = _complete_text(_make_completer(), "tl list ")
        assert "friends" in results
        assert "family" in results

    def test_tl_list_prefix_filter(self):
        with patch("misskey_cli.config.get_active_list_id", return_value=None):
            results = _complete_text(_make_completer(), "tl list fr")
        assert results == ["friends"]

    def test_default_timeline_list_offers_list_names(self):
        with patch("misskey_cli.config.get_active_list_id", return_value=None):
            results = _complete_text(_make_completer(), "default_timeline list ")
        assert "friends" in results
        assert "family" in results

    def test_list_use_still_works(self):
        """Regression: the new helper shouldn't break the original `list use` path."""
        with patch("misskey_cli.config.get_active_list_id", return_value=None):
            results = _complete_text(_make_completer(), "list use fr")
        assert results == ["friends"]

    # --- cmd-level parsing ---

    def test_cmd_tl_list_with_target_name(self):
        cli, stub = _build_stub_cli()
        cli.cmd_tl("list friends")
        stub.timeline.assert_called_once_with("list", 10, list_id="abc")

    def test_cmd_tl_list_with_target_and_limit(self):
        cli, stub = _build_stub_cli()
        cli.cmd_tl("list family 25")
        stub.timeline.assert_called_once_with("list", 25, list_id="def")

    def test_cmd_tl_list_bare_limit_uses_active(self):
        """`tl list 5` (bare number) must use the active list, not treat 5 as a target."""
        cli, stub = _build_stub_cli()
        with patch("misskey_cli.config.get_active_list_id", return_value="abc"):
            cli.cmd_tl("list 5")
        stub.timeline.assert_called_once_with("list", 5, list_id="abc")

    def test_cmd_tl_list_no_arg_uses_active(self):
        cli, stub = _build_stub_cli()
        with patch("misskey_cli.config.get_active_list_id", return_value="def"):
            cli.cmd_tl("list")
        stub.timeline.assert_called_once_with("list", 10, list_id="def")

    def test_cmd_tl_list_not_found_does_not_call_api(self):
        cli, stub = _build_stub_cli()
        cli.cmd_tl("list nonexistent")
        stub.timeline.assert_not_called()

    def test_cmd_tl_list_no_active_no_arg_errors(self):
        cli, stub = _build_stub_cli()
        with patch("misskey_cli.config.get_active_list_id", return_value=None):
            cli.cmd_tl("list")
        stub.timeline.assert_not_called()

    def test_cmd_default_timeline_list_with_target(self):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_active_list_id") as set_act, \
             patch("misskey_cli.config.set_default_timeline") as set_def, \
             patch("misskey_cli.config.get_active_list_id", return_value=None):
            cli.cmd_default_timeline("list friends")
        set_act.assert_called_once_with("abc")
        set_def.assert_called_once_with("list")

    def test_cmd_default_timeline_list_without_target_and_no_active_errors(self):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_active_list_id") as set_act, \
             patch("misskey_cli.config.set_default_timeline") as set_def, \
             patch("misskey_cli.config.get_active_list_id", return_value=None):
            cli.cmd_default_timeline("list")
        set_act.assert_not_called()
        set_def.assert_not_called()

    def test_cmd_tl_non_list_still_accepts_limit(self):
        """Regression: `tl home 20` must keep working unchanged."""
        cli, stub = _build_stub_cli()
        cli.cmd_tl("home 20")
        stub.timeline.assert_called_once_with("home", 20)


# ---------- CLI: run_script (non-interactive scripting) ----------


class TestRunScript:
    """Covers ``MisskeyCLI.run_script`` — the non-interactive entry point
    used by ``-c`` / ``-f`` / piped stdin.
    """

    def test_dispatches_to_handler(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["note_text public hello"])
        assert ok is True
        stub.create_note.assert_called_once()
        assert stub.create_note.call_args[0][0] == "hello"

    def test_multiple_lines_run_in_order(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script([
            "note_text public one",
            "note_text public two",
        ])
        assert ok is True
        assert stub.create_note.call_count == 2

    def test_blank_lines_are_skipped(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["", "   ", "note_text public hi", ""])
        assert ok is True
        stub.create_note.assert_called_once()

    def test_comments_are_skipped(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script([
            "# this is a comment",
            "  # indented comment",
            "note_text public hi",
        ])
        assert ok is True
        stub.create_note.assert_called_once()

    def test_unknown_command_sets_error(self, capsys):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["bogus foo"])
        assert ok is False
        captured = capsys.readouterr()
        assert "bogus" in captured.err
        # The error must go to stderr, not stdout.
        assert "bogus" not in captured.out

    def test_unknown_command_does_not_halt_script(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["bogus", "note_text public hi"])
        assert ok is False
        # second line still ran
        stub.create_note.assert_called_once()

    def test_quit_halts_execution(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script([
            "note_text public before",
            "quit",
            "note_text public after",
        ])
        assert ok is True
        assert stub.create_note.call_count == 1

    def test_exit_halts_execution(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script([
            "note_text public before",
            "exit",
            "note_text public after",
        ])
        assert ok is True
        assert stub.create_note.call_count == 1

    def test_handler_exception_is_caught(self, capsys):
        """If a command raises, run_script reports it via _error and keeps going."""
        cli, stub = _build_stub_cli()
        # First call raises, second succeeds.
        stub.create_note.side_effect = [
            RuntimeError("boom"),
            {"createdNote": {"id": "n2", "text": "ok", "visibility": "public"}},
        ]
        ok = cli.run_script([
            "note_text public first",
            "note_text public second",
        ])
        assert ok is False
        captured = capsys.readouterr()
        # cmd_note_text has its own try/except that swallows to _error — the
        # outer run_script try/except is a fallback for handlers that don't
        # catch their own exceptions. Either way, the error lands on stderr.
        assert "boom" in captured.err
        # The script did not halt on the exception.
        assert stub.create_note.call_count == 2

    def test_error_resets_between_runs(self):
        cli, stub = _build_stub_cli()
        assert cli.run_script(["bogus"]) is False
        # A subsequent successful run must report success.
        assert cli.run_script(["note_text public hi"]) is True

    def test_usage_error_goes_to_stderr(self, capsys):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["note_text"])
        assert ok is False
        captured = capsys.readouterr()
        assert "Usage" in captured.err or "note_text" in captured.err
        stub.create_note.assert_not_called()

    def test_not_logged_in_error_goes_to_stderr(self, capsys):
        cli, stub = _build_stub_cli()
        stub.logged_in = False
        ok = cli.run_script(["note_text public hi"])
        assert ok is False
        captured = capsys.readouterr()
        assert captured.err  # something was printed to stderr
        stub.create_note.assert_not_called()


# ---------- CLI: Mastodon-style aliases ----------


class TestAliases:
    """Covers the Mastodon-style command aliases (``post`` / ``toot`` /
    ``boost`` / ``whoami``). Aliases must dispatch to the canonical handler,
    show up in tab completion, and appear in ``help`` output.
    """

    def test_aliases_table_is_non_empty(self):
        # Sanity check: the canonical targets must actually exist as commands.
        assert ALIASES
        for alias, canonical in ALIASES.items():
            assert alias not in COMMANDS, f"alias {alias} collides with a real command"
            assert canonical in COMMANDS, f"alias {alias} targets missing command {canonical}"

    def test_post_alias_dispatches_to_note_text(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["post_text public hello via post_text"])
        assert ok is True
        stub.create_note.assert_called_once()
        assert stub.create_note.call_args[0][0] == "hello via post_text"

    def test_toot_alias_dispatches_to_note_text(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["toot_text public hello via toot_text"])
        assert ok is True
        stub.create_note.assert_called_once()
        assert stub.create_note.call_args[0][0] == "hello via toot_text"

    def test_boost_alias_dispatches_to_renote(self):
        cli, stub = _build_stub_cli()
        stub.renote.return_value = {"createdNote": {"id": "n2"}}
        ok = cli.run_script(["boost abc123"])
        assert ok is True
        stub.renote.assert_called_once_with("abc123")

    def test_whoami_alias_dispatches_to_i(self):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["whoami"])
        assert ok is True
        # client.i() is invoked once at construction and again by cmd_i.
        assert stub.i.call_count >= 1

    def test_unknown_alias_is_still_unknown(self, capsys):
        cli, stub = _build_stub_cli()
        ok = cli.run_script(["yeet hello world"])
        assert ok is False
        assert "yeet" in capsys.readouterr().err

    def test_completer_offers_aliases_on_empty_word(self):
        results = _complete_text(_make_completer(lists=[]), "")
        # Mastodon-style aliases are listed alongside the canonical commands.
        for name in ("post", "toot", "boost", "whoami", "note", "renote"):
            assert name in results

    def test_completer_prefix_filters_alias(self):
        results = _complete_text(_make_completer(lists=[]), "too")
        assert "toot" in results
        assert "toot_text" in results

    def test_completer_normalizes_alias_for_arg_completion(self):
        """After an alias, arg-position completion must behave like the canonical."""
        # ``post <tab>`` should offer visibilities (same as ``note <tab>``).
        results = _complete_text(_make_completer(lists=[]), "post ")
        for vis in ("public", "home", "followers", "specified"):
            assert vis in results

    def test_completer_boost_offers_note_ids(self):
        completer = _make_completer(
            note_meta=[{"id": "xyz789", "username": "alice", "snippet": "hi"}],
            lists=[],
        )
        results = _complete_text(completer, "boost ")
        assert "xyz789" in results

    def test_help_lists_aliases(self, capsys):
        cli, _ = _build_stub_cli()
        cli.cmd_help("")
        out = capsys.readouterr().out
        # Each alias appears on its own line with its canonical target.
        for alias in ALIASES:
            assert alias in out
        # The section header from the i18n catalog also appears.
        assert "Aliases" in out or "エイリアス" in out or "Alias" in out


# ---------- image.rgb_to_256 ----------


class TestRgbTo256:
    def test_pure_black(self):
        from misskey_cli.image import rgb_to_256
        assert rgb_to_256(0, 0, 0) == 16

    def test_pure_white(self):
        from misskey_cli.image import rgb_to_256
        assert rgb_to_256(255, 255, 255) == 231

    def test_pure_red(self):
        from misskey_cli.image import rgb_to_256
        # 16 + 36*5 + 6*0 + 0 = 196
        assert rgb_to_256(255, 0, 0) == 196

    def test_pure_green(self):
        from misskey_cli.image import rgb_to_256
        # 16 + 0 + 6*5 + 0 = 46
        assert rgb_to_256(0, 255, 0) == 46

    def test_pure_blue(self):
        from misskey_cli.image import rgb_to_256
        # 16 + 0 + 0 + 5 = 21
        assert rgb_to_256(0, 0, 255) == 21

    def test_very_dark_gray_clamps_to_16(self):
        from misskey_cli.image import rgb_to_256
        assert rgb_to_256(4, 4, 4) == 16

    def test_very_bright_gray_clamps_to_231(self):
        from misskey_cli.image import rgb_to_256
        assert rgb_to_256(250, 250, 250) == 231

    def test_midrange_gray_is_in_grayscale_ramp(self):
        from misskey_cli.image import rgb_to_256
        # Grayscale ramp is 232..255.
        idx = rgb_to_256(128, 128, 128)
        assert 232 <= idx <= 255


# ---------- image.render_image_256 ----------


class TestRenderImage256:
    def _png_bytes(self, size, color):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", size, color).save(buf, "PNG")
        return buf.getvalue()

    def test_tiny_image_produces_escape_codes_and_half_block(self):
        from misskey_cli.image import render_image_256
        out = render_image_256(self._png_bytes((2, 2), (255, 0, 0)), max_width=80)
        assert "\u2580" in out
        assert "\x1b[38;5;196m" in out  # red fg
        # Every line ends with the SGR reset + newline.
        assert "\x1b[0m\n" in out

    def test_odd_height_pads_bottom(self):
        from misskey_cli.image import render_image_256
        out = render_image_256(self._png_bytes((2, 3), (255, 255, 255)), max_width=80)
        # 3 rows → ceil(3/2) = 2 output lines.
        assert out.count("\n") == 2

    def test_resize_caps_width(self):
        from misskey_cli.image import render_image_256
        out = render_image_256(self._png_bytes((400, 10), (0, 0, 0)), max_width=20)
        for line in out.rstrip("\n").split("\n"):
            assert line.count("\u2580") <= 20


# ---------- MisskeyClient._normalize_files ----------


class TestMisskeyNormalizeFiles:
    def test_image_mime_maps_to_image(self):
        out = MisskeyClient._normalize_files([
            {
                "url": "u",
                "type": "image/png",
                "isSensitive": False,
                "comment": "cat",
                "properties": {"width": 10, "height": 20},
            }
        ])
        assert out == [{
            "url": "u",
            "type": "image",
            "sensitive": False,
            "alt": "cat",
            "width": 10,
            "height": 20,
        }]

    def test_video_mime(self):
        out = MisskeyClient._normalize_files([{"url": "u", "type": "video/mp4"}])
        assert out[0]["type"] == "video"

    def test_audio_mime(self):
        out = MisskeyClient._normalize_files([{"url": "u", "type": "audio/mpeg"}])
        assert out[0]["type"] == "audio"

    def test_unknown_mime_becomes_file(self):
        out = MisskeyClient._normalize_files([{"url": "u", "type": "application/pdf"}])
        assert out[0]["type"] == "file"

    def test_sensitive_flag_passthrough(self):
        out = MisskeyClient._normalize_files([
            {"url": "u", "type": "image/png", "isSensitive": True}
        ])
        assert out[0]["sensitive"] is True

    def test_missing_url_is_dropped(self):
        out = MisskeyClient._normalize_files([{"type": "image/png"}])
        assert out == []

    def test_empty_input(self):
        assert MisskeyClient._normalize_files(None) == []
        assert MisskeyClient._normalize_files([]) == []


# ---------- MisskeyClient file injection on returned notes ----------


class TestMisskeyInjectsFiles:
    def test_show_note_injects_files(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"{}",
                json=lambda: {
                    "id": "1",
                    "files": [
                        {"url": "https://m.example/a.png", "type": "image/png"},
                    ],
                },
            )
            note = c.show_note("1")
            assert note["files"] == [{
                "url": "https://m.example/a.png",
                "type": "image",
                "sensitive": False,
                "alt": None,
                "width": None,
                "height": None,
            }]

    def test_show_note_none_is_safe(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200, content=b"", json=lambda: None
            )
            assert c.show_note("1") is None

    def test_timeline_injects_files_on_each_note(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {"id": "1", "files": [{"url": "u1", "type": "image/png"}]},
                    {"id": "2", "files": []},
                ],
            )
            notes = c.timeline("home", limit=2)
            assert notes[0]["files"][0]["type"] == "image"
            assert notes[1]["files"] == []

    def test_notifications_injects_files_on_embedded_note(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"[]",
                json=lambda: [
                    {
                        "id": "n",
                        "type": "reply",
                        "note": {
                            "id": "a",
                            "files": [{"url": "u", "type": "image/png"}],
                        },
                    }
                ],
            )
            notifs = c.notifications(limit=1)
            assert notifs[0]["note"]["files"][0]["type"] == "image"

    def test_show_note_normalizes_inner_renote_files(self):
        c = MisskeyClient(host="m.example", token="t", scheme="http")
        with patch("misskey_cli.api.requests.post") as post:
            post.return_value = MagicMock(
                status_code=200,
                content=b"{}",
                json=lambda: {
                    "id": "1",
                    "renote": {
                        "id": "rn",
                        "files": [{"url": "u", "type": "video/mp4"}],
                    },
                },
            )
            note = c.show_note("1")
            assert note["renote"]["files"][0]["type"] == "video"


# ---------- MastodonClient._normalize_files_mastodon ----------


class TestMastodonNormalizeFiles:
    def test_image_maps_through(self):
        out = MastodonClient._normalize_files_mastodon(
            [{
                "url": "https://x/a.png",
                "type": "image",
                "description": "alt",
                "meta": {"original": {"width": 100, "height": 50}},
            }],
            note_sensitive=False,
        )
        assert out == [{
            "url": "https://x/a.png",
            "type": "image",
            "sensitive": False,
            "alt": "alt",
            "width": 100,
            "height": 50,
        }]

    def test_gifv_stays_distinct_from_image(self):
        out = MastodonClient._normalize_files_mastodon(
            [{"url": "https://x/g.mp4", "type": "gifv"}],
            note_sensitive=False,
        )
        assert out[0]["type"] == "gifv"

    def test_unknown_type_becomes_file(self):
        out = MastodonClient._normalize_files_mastodon(
            [{"url": "https://x/u.bin", "type": "unknown"}],
            note_sensitive=False,
        )
        assert out[0]["type"] == "file"

    def test_note_level_sensitive_propagates(self):
        out = MastodonClient._normalize_files_mastodon(
            [{"url": "https://x/a.png", "type": "image"}],
            note_sensitive=True,
        )
        assert out[0]["sensitive"] is True

    def test_empty_input(self):
        assert MastodonClient._normalize_files_mastodon(None, False) == []
        assert MastodonClient._normalize_files_mastodon([], False) == []

    def test_normalize_note_carries_files(self):
        c = _client("mastodon")
        note = c._normalize_note({
            "id": "1",
            "created_at": "2024-01-01T00:00:00Z",
            "account": {"id": "2", "username": "alice", "acct": "alice"},
            "content": "<p>hi</p>",
            "visibility": "public",
            "sensitive": True,
            "media_attachments": [
                {"url": "https://x/a.png", "type": "image", "description": "alt"},
            ],
        })
        assert note["files"] == [{
            "url": "https://x/a.png",
            "type": "image",
            "sensitive": True,
            "alt": "alt",
            "width": None,
            "height": None,
        }]

    def test_normalize_note_no_media_returns_empty_list(self):
        c = _client("mastodon")
        note = c._normalize_note({
            "id": "1",
            "created_at": "2024-01-01T00:00:00Z",
            "account": {"id": "2", "username": "alice", "acct": "alice"},
            "content": "<p>hi</p>",
            "visibility": "public",
        })
        assert note["files"] == []


# ---------- _format_note attachment footer ----------


class TestFormatNoteAttachments:
    def _base_note(self, **over):
        note = {
            "id": "n1",
            "createdAt": "2024-01-01T00:00:00Z",
            "user": {"username": "alice", "name": "Alice"},
            "text": "hi",
            "reactions": {},
        }
        note.update(over)
        return note

    def test_no_files_no_marker_line(self):
        from misskey_cli.cli import _format_note
        joined = "".join(t for _, t in _format_note(self._base_note()))
        assert "\U0001f4ce" not in joined

    def test_empty_files_no_marker_line(self):
        from misskey_cli.cli import _format_note
        joined = "".join(
            t for _, t in _format_note(self._base_note(files=[]))
        )
        assert "\U0001f4ce" not in joined

    def test_files_produce_marker_line(self):
        from misskey_cli.cli import _format_note
        note = self._base_note(files=[
            {"url": "u", "type": "image", "sensitive": False},
            {"url": "u2", "type": "video", "sensitive": True},
        ])
        joined = "".join(t for _, t in _format_note(note))
        assert "\U0001f4ce" in joined
        assert "[1]image" in joined
        assert "[2]video NSFW" in joined

    def test_files_line_uses_ansiblue_style(self):
        from misskey_cli.cli import _format_note
        note = self._base_note(files=[{"url": "u", "type": "image"}])
        parts = _format_note(note)
        # Find the attachment line — the one containing the clip marker.
        attachment_parts = [
            (style, text) for style, text in parts if "\U0001f4ce" in text
        ]
        assert attachment_parts
        assert attachment_parts[0][0] == "ansiblue"


# ---------- cmd_preview ----------


class TestCmdPreview:
    def test_no_arg_errors(self, capsys):
        cli, stub = _build_stub_cli()
        cli.cmd_preview("")
        assert capsys.readouterr().err
        stub.show_note.assert_not_called()

    def test_not_logged_in_errors(self, capsys):
        cli, stub = _build_stub_cli()
        stub.logged_in = False
        cli.cmd_preview("n1")
        assert capsys.readouterr().err
        stub.show_note.assert_not_called()

    def test_note_without_images_errors(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {"id": "n1", "files": []}
        cli.cmd_preview("n1")
        assert capsys.readouterr().err

    def test_non_integer_index_errors(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "u", "type": "image"}],
        }
        cli.cmd_preview("n1 xyz")
        assert capsys.readouterr().err
        # Render should not have been attempted.
        with patch("misskey_cli.image.render_image_from_url_auto") as render:
            render.assert_not_called()

    def test_zero_index_errors(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "u", "type": "image"}],
        }
        cli.cmd_preview("n1 0")
        assert capsys.readouterr().err

    def test_index_out_of_range(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "u", "type": "image"}],
        }
        cli.cmd_preview("n1 5")
        err = capsys.readouterr().err
        assert "5" in err

    def test_happy_path_renders_image(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [
                {"url": "https://x/a.png", "type": "image", "alt": None},
            ],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            return_value="\x1b[38;5;196m\u2580\x1b[0m\n",
        ) as render, patch(
            "misskey_cli.config.get_image_backend", return_value="auto"
        ):
            cli.cmd_preview("n1")
            render.assert_called_once()
            assert render.call_args[0][0] == "https://x/a.png"
        out = capsys.readouterr().out
        assert "\u2580" in out

    def test_alt_text_is_printed_below_image(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [
                {"url": "https://x/a.png", "type": "image", "alt": "a cat"},
            ],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            return_value="",
        ), patch(
            "misskey_cli.config.get_image_backend", return_value="auto"
        ):
            cli.cmd_preview("n1")
        out = capsys.readouterr().out
        assert "a cat" in out

    def test_fetch_failure_routes_to_error(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.side_effect = RuntimeError("boom")
        cli.cmd_preview("n1")
        assert "boom" in capsys.readouterr().err

    def test_render_failure_routes_to_preview_failed(self, capsys):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "https://x/a.png", "type": "image"}],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            side_effect=RuntimeError("decode fail"),
        ), patch(
            "misskey_cli.config.get_image_backend", return_value="auto"
        ):
            cli.cmd_preview("n1")
        assert "decode fail" in capsys.readouterr().err

    def test_index_is_into_image_only_subset(self):
        """``preview n1 2`` must render the SECOND IMAGE, not the second file,
        when the note mixes image and non-image attachments."""
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [
                {"url": "https://x/v.mp4", "type": "video"},
                {"url": "https://x/a.png", "type": "image"},
                {"url": "https://x/b.png", "type": "image"},
            ],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            return_value="",
        ) as render, patch(
            "misskey_cli.config.get_image_backend", return_value="auto"
        ):
            cli.cmd_preview("n1 2")
            render.assert_called_once()
            # The 2nd IMAGE (b.png), not the 2nd file (a.png).
            assert render.call_args[0][0] == "https://x/b.png"

    def test_preview_reads_image_backend_from_config(self):
        """cmd_preview must forward the current image_backend setting."""
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "https://x/a.png", "type": "image"}],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            return_value="",
        ) as render, patch(
            "misskey_cli.config.get_image_backend",
            return_value="sixel",
        ):
            cli.cmd_preview("n1")
        assert render.call_args.kwargs["backend"] == "sixel"

    def test_preview_auto_backend_is_default(self):
        cli, stub = _build_stub_cli()
        stub.show_note.return_value = {
            "id": "n1",
            "files": [{"url": "https://x/a.png", "type": "image"}],
        }
        with patch(
            "misskey_cli.image.render_image_from_url_auto",
            return_value="",
        ) as render, patch(
            "misskey_cli.config.get_image_backend",
            return_value="auto",
        ):
            cli.cmd_preview("n1")
        assert render.call_args.kwargs["backend"] == "auto"


# ---------- Completer & help for preview ----------


def test_completer_preview_offers_note_ids():
    completer = _make_completer(
        note_meta=[{"id": "n42", "username": "alice", "snippet": "hi"}],
        lists=[],
    )
    results = _complete_text(completer, "preview ")
    assert "n42" in results


def test_help_lists_preview(capsys):
    cli, _ = _build_stub_cli()
    cli.cmd_help("")
    assert "preview" in capsys.readouterr().out


# ---------- Graphics backend detection ----------


def _stub_tty(stdin_is_tty=True, stdout_is_tty=True, read_response=""):
    """Build a fake sys.stdin / sys.stdout pair for the DA1 probe.

    ``read_response`` is handed out one character at a time from ``read(1)``.
    """
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = stdin_is_tty
    fake_stdin.fileno.return_value = 0
    chars = iter(read_response)
    fake_stdin.read.side_effect = lambda n: next(chars, "")

    fake_stdout = MagicMock()
    fake_stdout.isatty.return_value = stdout_is_tty
    fake_stdout.write = MagicMock()
    fake_stdout.flush = MagicMock()
    return fake_stdin, fake_stdout


class TestDetectGraphicsBackend:
    """Tests for :func:`misskey_cli.image.detect_graphics_backend`."""

    def setup_method(self):
        from misskey_cli import image

        image._reset_backend_cache_for_tests()

    def teardown_method(self):
        from misskey_cli import image

        image._reset_backend_cache_for_tests()

    def test_kitty_env_wins(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        assert image.detect_graphics_backend() == "kitty"

    def test_ghostty_env(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "ghostty")
        assert image.detect_graphics_backend() == "kitty"

    def test_wezterm_env(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
        assert image.detect_graphics_backend() == "kitty"

    def test_no_env_no_tty_returns_none(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        fake_stdin, fake_stdout = _stub_tty(stdin_is_tty=False)
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        assert image.detect_graphics_backend() == "none"
        fake_stdout.write.assert_not_called()

    def test_tmux_bails_without_probe(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "tmux-256color")
        fake_stdin, fake_stdout = _stub_tty()
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        assert image.detect_graphics_backend() == "none"
        fake_stdout.write.assert_not_called()

    def test_screen_bails_without_probe(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "screen.xterm-256color")
        fake_stdin, fake_stdout = _stub_tty()
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        assert image.detect_graphics_backend() == "none"
        fake_stdout.write.assert_not_called()

    def test_probe_response_with_sixel_token(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        fake_stdin, fake_stdout = _stub_tty(
            read_response="\x1b[?64;1;2;4;6;9;15;22c"
        )
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcgetattr", lambda fd: "saved"
        )
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcsetattr", lambda fd, when, attrs: None
        )
        monkeypatch.setattr("misskey_cli.image.tty.setcbreak", lambda fd: None)
        monkeypatch.setattr(
            "misskey_cli.image.select.select",
            lambda r, w, x, t: ([fake_stdin], [], []),
        )
        assert image.detect_graphics_backend() == "sixel"

    def test_probe_response_without_sixel_token(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        fake_stdin, fake_stdout = _stub_tty(
            read_response="\x1b[?64;1;2;6;9;22c"
        )
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcgetattr", lambda fd: "saved"
        )
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcsetattr", lambda fd, when, attrs: None
        )
        monkeypatch.setattr("misskey_cli.image.tty.setcbreak", lambda fd: None)
        monkeypatch.setattr(
            "misskey_cli.image.select.select",
            lambda r, w, x, t: ([fake_stdin], [], []),
        )
        assert image.detect_graphics_backend() == "none"

    def test_probe_token_split_not_substring(self, monkeypatch):
        """``14``/``40``/``42`` must NOT count as sixel (no literal ``4`` token)."""
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        fake_stdin, fake_stdout = _stub_tty(
            read_response="\x1b[?14;1;2;40;42c"
        )
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcgetattr", lambda fd: "saved"
        )
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcsetattr", lambda fd, when, attrs: None
        )
        monkeypatch.setattr("misskey_cli.image.tty.setcbreak", lambda fd: None)
        monkeypatch.setattr(
            "misskey_cli.image.select.select",
            lambda r, w, x, t: ([fake_stdin], [], []),
        )
        assert image.detect_graphics_backend() == "none"

    def test_probe_timeout(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        fake_stdin, fake_stdout = _stub_tty()
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcgetattr", lambda fd: "saved"
        )
        monkeypatch.setattr(
            "misskey_cli.image.termios.tcsetattr", lambda fd, when, attrs: None
        )
        monkeypatch.setattr("misskey_cli.image.tty.setcbreak", lambda fd: None)
        monkeypatch.setattr(
            "misskey_cli.image.select.select",
            lambda r, w, x, t: ([], [], []),  # timeout
        )
        assert image.detect_graphics_backend() == "none"

    def test_probe_defensive_exception(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        fake_stdin, fake_stdout = _stub_tty()
        monkeypatch.setattr("sys.stdin", fake_stdin)
        monkeypatch.setattr("sys.stdout", fake_stdout)

        def boom(fd):
            raise OSError("not a tty")

        monkeypatch.setattr("misskey_cli.image.termios.tcgetattr", boom)
        assert image.detect_graphics_backend() == "none"

    def test_cached_result_reused(self, monkeypatch):
        from misskey_cli import image

        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        assert image.detect_graphics_backend() == "kitty"
        # Remove the env var; cache should still return kitty.
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        assert image.detect_graphics_backend() == "kitty"


# ---------- Sixel and Kitty renderers ----------


def _tiny_red_png():
    from PIL import Image

    img = Image.new("RGB", (2, 2), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _larger_png():
    """Noisy multi-kilobyte PNG so Kitty chunking exercises the multi-segment path.

    A solid-color PNG would compress below the 4096-byte chunk threshold.
    This uses pseudo-random RGB bytes (deterministic seed) so the encoded
    PNG is large enough to require several APC segments.
    """
    import random

    from PIL import Image

    rng = random.Random(0xC0FFEE)
    size = 100
    data = bytes(rng.randrange(256) for _ in range(size * size * 3))
    img = Image.frombytes("RGB", (size, size), data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestRenderImageSixel:
    def test_outputs_sixel_string(self):
        from misskey_cli import image

        out = image.render_image_sixel(_tiny_red_png(), max_pixel_width=64)
        assert isinstance(out, str)
        assert out.startswith("\x1bP")  # DCS introducer
        assert out.endswith("\x1b\\")  # ST

    def test_passes_max_pixel_width(self):
        from misskey_cli import image

        with patch("sixel.converter.SixelConverter") as SC:
            SC.return_value.getvalue.return_value = "stub"
            image.render_image_sixel(b"dummy", max_pixel_width=123)
            assert SC.call_args.kwargs["w"] == 123


class TestRenderImageKitty:
    def test_small_image_has_kitty_header(self):
        from misskey_cli import image

        out = image.render_image_kitty(_tiny_red_png(), max_cols=20)
        assert out.startswith("\x1b_Ga=T,f=100,c=20,m=")
        assert out.endswith("\x1b\\\n")

    def test_small_image_single_chunk_is_m0(self):
        from misskey_cli import image

        out = image.render_image_kitty(_tiny_red_png(), max_cols=20)
        # Tiny PNG fits in a single <4096 byte base64 chunk.
        assert out.count("\x1b_G") == 1
        assert ",m=0;" in out

    def test_large_image_is_chunked(self):
        from misskey_cli import image

        png = _larger_png()
        out = image.render_image_kitty(png, max_cols=40)
        # Verify there's more than one APC segment.
        assert out.count("\x1b_G") >= 2
        # Last chunk is m=0, earlier ones m=1.
        assert ";m=0;" in out or "m=0;" in out
        # Every segment opens with _G and closes with \\.
        parts = out.rstrip("\n").split("\x1b\\")
        parts = [p for p in parts if p]
        for p in parts:
            assert p.startswith("\x1b_G")

    def test_base64_payload_roundtrips_to_png(self):
        import base64 as b64
        import re

        from misskey_cli import image

        png_in = _larger_png()
        out = image.render_image_kitty(png_in, max_cols=40)
        # Extract all payloads between ';' and the ST terminator.
        segs = re.findall(r"\x1b_G[^;]*;([^\x1b]*)\x1b\\", out)
        assert segs, "no APC segments found"
        joined = "".join(segs)
        decoded = b64.standard_b64decode(joined)
        # Pillow re-encodes so bytes won't equal the input, but the result
        # must still be a valid PNG (starts with the PNG magic).
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


class TestRenderImageAutoDispatch:
    def setup_method(self):
        from misskey_cli import image

        image._reset_backend_cache_for_tests()

    def teardown_method(self):
        from misskey_cli import image

        image._reset_backend_cache_for_tests()

    def test_explicit_256(self):
        from misskey_cli import image

        with patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            r256.return_value = "256"
            image.render_image_auto(b"x", max_cols=80, backend="256")
        r256.assert_called_once()
        rsx.assert_not_called()
        rkt.assert_not_called()

    def test_explicit_sixel(self):
        from misskey_cli import image

        with patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            rsx.return_value = "sixel"
            image.render_image_auto(b"x", max_cols=80, backend="sixel")
        rsx.assert_called_once()
        r256.assert_not_called()
        rkt.assert_not_called()

    def test_explicit_kitty(self):
        from misskey_cli import image

        with patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            rkt.return_value = "kitty"
            image.render_image_auto(b"x", max_cols=80, backend="kitty")
        rkt.assert_called_once()
        r256.assert_not_called()
        rsx.assert_not_called()

    def test_auto_picks_kitty_when_detected(self):
        from misskey_cli import image

        with patch(
            "misskey_cli.image.detect_graphics_backend", return_value="kitty"
        ), patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            rkt.return_value = "kitty"
            image.render_image_auto(b"x", max_cols=80, backend="auto")
        rkt.assert_called_once()
        r256.assert_not_called()
        rsx.assert_not_called()

    def test_auto_picks_sixel_when_detected(self):
        from misskey_cli import image

        with patch(
            "misskey_cli.image.detect_graphics_backend", return_value="sixel"
        ), patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            rsx.return_value = "sixel"
            image.render_image_auto(b"x", max_cols=80, backend="auto")
        rsx.assert_called_once()
        r256.assert_not_called()
        rkt.assert_not_called()

    def test_auto_falls_back_to_256(self):
        from misskey_cli import image

        with patch(
            "misskey_cli.image.detect_graphics_backend", return_value="none"
        ), patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            r256.return_value = "256"
            image.render_image_auto(b"x", max_cols=80, backend="auto")
        r256.assert_called_once()
        rsx.assert_not_called()
        rkt.assert_not_called()

    def test_unknown_backend_falls_back_to_256(self):
        from misskey_cli import image

        with patch("misskey_cli.image.render_image_256") as r256, \
             patch("misskey_cli.image.render_image_sixel") as rsx, \
             patch("misskey_cli.image.render_image_kitty") as rkt:
            r256.return_value = "256"
            image.render_image_auto(b"x", max_cols=80, backend="bogus")
        r256.assert_called_once()
        rsx.assert_not_called()
        rkt.assert_not_called()

    def test_sixel_pixel_width_derived_from_cols(self):
        from misskey_cli import image

        with patch("misskey_cli.image.render_image_sixel") as rsx:
            rsx.return_value = ""
            image.render_image_auto(b"x", max_cols=80, backend="sixel")
        # 80 cols * CELL_PIXEL_WIDTH (10) = 800 px
        assert rsx.call_args.kwargs["max_pixel_width"] == 800


# ---------- image_backend command ----------


class TestCmdImageBackend:
    def test_show_current(self, capsys):
        cli, _ = _build_stub_cli()
        with patch(
            "misskey_cli.config.get_image_backend", return_value="auto"
        ):
            cli.cmd_image_backend("")
        out = capsys.readouterr().out
        assert "auto" in out

    def test_set_sixel(self):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_image_backend") as set_ib:
            cli.cmd_image_backend("sixel")
        set_ib.assert_called_once_with("sixel")

    def test_set_kitty(self):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_image_backend") as set_ib:
            cli.cmd_image_backend("kitty")
        set_ib.assert_called_once_with("kitty")

    def test_set_256(self):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_image_backend") as set_ib:
            cli.cmd_image_backend("256")
        set_ib.assert_called_once_with("256")

    def test_invalid_value_errors(self, capsys):
        cli, _ = _build_stub_cli()
        with patch("misskey_cli.config.set_image_backend") as set_ib:
            cli.cmd_image_backend("bogus")
        assert capsys.readouterr().err
        set_ib.assert_not_called()

    def test_does_not_require_login(self):
        """image_backend is a terminal setting, not account-bound."""
        cli, stub = _build_stub_cli()
        stub.logged_in = False
        with patch("misskey_cli.config.set_image_backend") as set_ib:
            cli.cmd_image_backend("sixel")
        set_ib.assert_called_once_with("sixel")


def test_completer_image_backend_offers_all_choices():
    completer = _make_completer()
    results = _complete_text(completer, "image_backend ")
    assert "auto" in results
    assert "sixel" in results
    assert "kitty" in results
    assert "256" in results


def test_completer_image_backend_prefix_filter():
    completer = _make_completer()
    results = _complete_text(completer, "image_backend si")
    assert "sixel" in results
    assert "auto" not in results
    assert "kitty" not in results


def test_help_lists_image_backend(capsys):
    cli, _ = _build_stub_cli()
    cli.cmd_help("")
    assert "image_backend" in capsys.readouterr().out


def test_main_probes_graphics_backend_once():
    """main.main() must probe the graphics backend once, before
    MisskeyCLI is constructed, so prompt_toolkit doesn't collide with
    the DA1 query."""
    from misskey_cli import main as main_mod

    call_order = []

    def fake_probe():
        call_order.append("probe")
        return "none"

    class FakeCLI:
        def __init__(self, *a, **kw):
            call_order.append("cli_init")

        def run_script(self, source):
            call_order.append("run_script")
            return True

        def cmdloop(self):
            call_order.append("cmdloop")

    with patch("misskey_cli.main.run_upgrade"), \
         patch("misskey_cli.main.init_language"), \
         patch("misskey_cli.image.detect_graphics_backend", side_effect=fake_probe), \
         patch("misskey_cli.main.MisskeyCLI", FakeCLI), \
         patch("sys.argv", ["misskey-cli", "-c", "help"]), \
         patch("sys.exit"):
        main_mod.main()

    assert call_order.index("probe") < call_order.index("cli_init")
    assert call_order.count("probe") == 1
