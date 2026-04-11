"""Unit tests for MastodonClient / detect_software (no network, no docker)."""
from unittest.mock import MagicMock, patch

import pytest

from misskey_cli.api import (
    MASTODON_SOFTWARE,
    MastodonClient,
    MisskeyClient,
    NekonoverseClient,
    detect_software,
    make_client,
)


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
