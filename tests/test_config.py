"""Tests for source-order resolution (reddit_scraper.config)."""
import pytest

from reddit_scraper import config


@pytest.fixture(autouse=True)
def reset_order():
    config.set_source_order(None)
    yield
    config.set_source_order(None)


class TestSourceOrder:

    def test_default_when_unset(self):
        config.set_source_order(None)
        assert config.get_source_order() == ['oauth', 'json', 'rss']

    def test_drops_invalid_names_and_keeps_order(self):
        config.set_source_order(['json', 'bogus', 'rss', 'oauth'])
        assert config.get_source_order() == ['json', 'rss', 'oauth']

    def test_empty_after_cleaning_falls_back_to_default(self):
        config.set_source_order(['nonsense', ''])
        assert config.get_source_order() == ['oauth', 'json', 'rss']

    def test_returns_a_copy(self):
        config.set_source_order(['rss'])
        order = config.get_source_order()
        order.append('json')
        assert config.get_source_order() == ['rss']  # internal state unchanged


class TestApplySourceOrderFromConfig:

    def test_config_source_order_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv('REDDIT_SOURCE_ORDER', 'json,rss')
        config.apply_source_order_from_config({'source_order': ['rss']})
        assert config.get_source_order() == ['rss']

    def test_falls_back_to_env_when_config_missing_key(self, monkeypatch):
        monkeypatch.setenv('REDDIT_SOURCE_ORDER', 'json,rss')
        config.apply_source_order_from_config({})
        assert config.get_source_order() == ['json', 'rss']

    def test_falls_back_to_default_when_neither_set(self, monkeypatch):
        monkeypatch.delenv('REDDIT_SOURCE_ORDER', raising=False)
        config.apply_source_order_from_config({})
        assert config.get_source_order() == ['oauth', 'json', 'rss']
