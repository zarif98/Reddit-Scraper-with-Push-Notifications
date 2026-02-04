"""Pytest configuration and fixtures for Reddit Monitor tests."""
import sys
import os
import tempfile
import json

# Create temp data dir and credentials BEFORE any imports of bot.py
_temp_dir = tempfile.mkdtemp()
os.environ['DATA_DIR'] = _temp_dir

# Create required files
_creds = {
    'reddit_client_id': 'test123',
    'reddit_client_secret': 'testsecret456',
    'reddit_username': 'testuser',
    'reddit_password': 'testpass',
    'reddit_user_agent': 'TestAgent/1.0',
    'notification_urls': [],
}
with open(os.path.join(_temp_dir, 'credentials.json'), 'w') as f:
    json.dump(_creds, f)
with open(os.path.join(_temp_dir, 'search.json'), 'w') as f:
    json.dump({'subreddits_to_search': []}, f)

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def sample_reddit_post():
    """Sample Reddit post data as returned by JSON endpoint."""
    return {
        'id': 'abc123',
        'title': '[USA-CA] [H] RTX 4090 [W] PayPal',
        'url': 'https://reddit.com/r/hardwareswap/comments/abc123',
        'score': 15,
        'permalink': '/r/hardwareswap/comments/abc123/usaca_h_rtx_4090_w_paypal/',
        'domain': 'self.hardwareswap',
        'link_flair_text': 'SELLING',
        'author': 'testuser',
    }


@pytest.fixture
def sample_monitor_config():
    """Sample monitor configuration."""
    return {
        'subreddit': 'hardwareswap',
        'keywords': ['4090'],
        'exclude_keywords': ['wanted'],
        'min_upvotes': 5,
        'domain_contains': [],
        'domain_excludes': [],
        'flair_contains': [],
        'author_includes': [],
        'author_excludes': [],
    }


@pytest.fixture
def mock_json_response():
    """Mock response from Reddit JSON endpoint."""
    return {
        'data': {
            'children': [
                {
                    'data': {
                        'id': 'post1',
                        'title': '[USA-NY] [H] RTX 4090 FE [W] PayPal',
                        'url': 'https://reddit.com/r/hardwareswap/comments/post1',
                        'score': 25,
                        'permalink': '/r/hardwareswap/comments/post1/',
                        'domain': 'self.hardwareswap',
                        'link_flair_text': 'SELLING',
                        'author': 'seller123',
                    }
                },
                {
                    'data': {
                        'id': 'post2',
                        'title': '[USA-TX] [H] PayPal [W] RTX 4080',
                        'url': 'https://reddit.com/r/hardwareswap/comments/post2',
                        'score': 10,
                        'permalink': '/r/hardwareswap/comments/post2/',
                        'domain': 'self.hardwareswap',
                        'link_flair_text': 'BUYING',
                        'author': 'buyer456',
                    }
                }
            ]
        }
    }
