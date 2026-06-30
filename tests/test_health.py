"""Tests for Uptime Kuma heartbeats (reddit_scraper.health)."""
import time

import pytest

from reddit_scraper import health, credentials, config, sources


@pytest.fixture
def captured(monkeypatch):
    """Capture outgoing heartbeat requests instead of hitting the network."""
    calls = []
    monkeypatch.setattr(health.requests, 'get', lambda url, params=None, **k: calls.append((url, params)))
    monkeypatch.delenv('KUMA_PUSH_URL', raising=False)
    monkeypatch.delenv('KUMA_FALLBACK_PUSH_URL', raising=False)
    saved = credentials.CREDENTIALS
    yield calls
    credentials.CREDENTIALS = saved
    config.set_source_order(None)


class TestOauthExpected:

    def test_true_when_app_creds_and_oauth_in_order(self):
        credentials.CREDENTIALS = {'reddit_client_id': 'a', 'reddit_client_secret': 'b'}
        config.set_source_order(['oauth', 'rss'])
        assert health._oauth_expected() is True

    def test_false_without_app_creds(self):
        credentials.CREDENTIALS = {}
        config.set_source_order(['oauth', 'rss'])
        assert health._oauth_expected() is False

    def test_false_when_oauth_not_in_order(self):
        credentials.CREDENTIALS = {'reddit_client_id': 'a', 'reddit_client_secret': 'b'}
        config.set_source_order(['rss', 'json'])
        assert health._oauth_expected() is False


class TestFallbackHeartbeat:

    def test_down_when_oauth_expected_but_on_fallback(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_FALLBACK_PUSH_URL', 'http://kuma/api/push/FB')
        credentials.CREDENTIALS = {'reddit_client_id': 'a', 'reddit_client_secret': 'b'}
        config.set_source_order(['oauth', 'rss', 'json'])
        sources._active_source = 'rss'
        health.send_kuma_fallback_heartbeat()
        assert captured[0][1]['status'] == 'down'

    def test_up_when_active_source_is_oauth(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_FALLBACK_PUSH_URL', 'http://kuma/api/push/FB')
        credentials.CREDENTIALS = {'reddit_client_id': 'a', 'reddit_client_secret': 'b'}
        config.set_source_order(['oauth', 'rss', 'json'])
        sources._active_source = 'oauth'
        health.send_kuma_fallback_heartbeat()
        assert captured[0][1]['status'] == 'up'

    def test_up_when_rss_is_intended(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_FALLBACK_PUSH_URL', 'http://kuma/api/push/FB')
        credentials.CREDENTIALS = {}            # no app -> RSS is by configuration
        sources._active_source = 'rss'
        health.send_kuma_fallback_heartbeat()
        assert captured[0][1]['status'] == 'up'

    def test_noop_when_url_unset(self, captured):
        health.send_kuma_fallback_heartbeat()
        assert captured == []


class TestPrimaryHeartbeat:

    def test_up_on_recent_success(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_PUSH_URL', 'http://kuma/api/push/MAIN')
        sources._LAST_FETCH_SUCCESS_TS = time.time()
        health.send_kuma_heartbeat()
        assert captured[0][1]['status'] == 'up'

    def test_down_when_never_succeeded(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_PUSH_URL', 'http://kuma/api/push/MAIN')
        sources._LAST_FETCH_SUCCESS_TS = None
        health.send_kuma_heartbeat()
        assert captured[0][1]['status'] == 'down'

    def test_down_when_stale(self, captured, monkeypatch):
        monkeypatch.setenv('KUMA_PUSH_URL', 'http://kuma/api/push/MAIN')
        monkeypatch.setenv('KUMA_FETCH_STALE_SECONDS', '60')
        sources._LAST_FETCH_SUCCESS_TS = time.time() - 600
        health.send_kuma_heartbeat()
        assert captured[0][1]['status'] == 'down'
