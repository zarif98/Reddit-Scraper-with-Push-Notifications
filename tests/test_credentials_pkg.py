"""Tests for credential loading, the encoding guard, and PRAW auth modes
(reddit_scraper.credentials)."""
import pytest

from reddit_scraper import credentials


@pytest.fixture(autouse=True)
def restore_state():
    saved_creds = credentials.CREDENTIALS
    saved_warning = credentials.CREDENTIAL_WARNING
    yield
    credentials.CREDENTIALS = saved_creds
    credentials.CREDENTIAL_WARNING = saved_warning


class TestCheckCredentialEncoding:

    def test_detects_cyrillic_lookalike(self):
        creds = {'reddit_client_secret': 'IaYQJWІRqNCg'}  # Cyrillic І at index 6
        offenders = credentials.check_credential_encoding(creds)
        assert offenders and 'reddit_client_secret' in offenders[0]
        assert credentials.CREDENTIAL_WARNING is not None
        assert 'Non-ASCII' in credentials.CREDENTIAL_WARNING

    def test_clean_credentials_clear_warning(self):
        credentials.CREDENTIAL_WARNING = "stale warning"
        offenders = credentials.check_credential_encoding({
            'reddit_client_id': 'abc', 'reddit_client_secret': 'def',
        })
        assert offenders == []
        assert credentials.CREDENTIAL_WARNING is None


class TestLoadCredentials:

    def test_env_fallback_when_no_file(self, monkeypatch):
        monkeypatch.setattr(credentials.config, 'get_credentials_path', lambda: '/nonexistent/creds.json')
        monkeypatch.setenv('REDDIT_CLIENT_ID', 'env_id')
        monkeypatch.setenv('REDDIT_CLIENT_SECRET', 'env_secret')
        creds = credentials.load_credentials()
        assert creds['reddit_client_id'] == 'env_id'
        assert creds['reddit_client_secret'] == 'env_secret'
        assert creds['notification_urls'] == []


class TestAuthenticateReddit:

    def test_returns_none_without_app_credentials(self):
        credentials.CREDENTIALS = {'reddit_client_id': None, 'reddit_client_secret': None}
        assert credentials.authenticate_reddit() is None

    def test_app_only_is_read_only(self):
        credentials.CREDENTIALS = {
            'reddit_client_id': 'id', 'reddit_client_secret': 'secret',
            'reddit_user_agent': 'ua/1.0',
        }
        reddit = credentials.authenticate_reddit()
        assert reddit is not None
        assert reddit.read_only is True

    def test_full_login_is_not_read_only(self):
        credentials.CREDENTIALS = {
            'reddit_client_id': 'id', 'reddit_client_secret': 'secret',
            'reddit_user_agent': 'ua/1.0',
            'reddit_username': 'user', 'reddit_password': 'pass',
        }
        reddit = credentials.authenticate_reddit()
        assert reddit is not None
        assert reddit.read_only is False
