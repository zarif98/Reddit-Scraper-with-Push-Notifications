"""Unit tests for bot.py functionality.

bot.py no longer does blocking/auth work at import time (the data-source helpers
live in the reddit_scraper package and are re-exported by bot), so these run normally.
"""
import responses


class TestFetchPostsJson:
    """Tests for fetch_posts_json function."""
    
    @responses.activate
    def test_fetch_posts_json_success(self, mock_json_response):
        """Test successful fetch from JSON endpoint."""
        from bot import fetch_posts_json
        
        responses.add(
            responses.GET,
            'https://old.reddit.com/r/hardwareswap/new.json?limit=10',
            json=mock_json_response,
            status=200
        )
        
        posts = fetch_posts_json('hardwareswap', limit=10)
        
        assert posts is not None
        assert len(posts) == 2
        assert posts[0]['id'] == 'post1'
        assert posts[0]['title'] == '[USA-NY] [H] RTX 4090 FE [W] PayPal'
        assert posts[0]['score'] == 25
        assert posts[1]['id'] == 'post2'
    
    @responses.activate
    def test_fetch_posts_json_rate_limited(self):
        """Test handling of rate limit (429) response."""
        from bot import fetch_posts_json
        
        responses.add(
            responses.GET,
            'https://old.reddit.com/r/hardwareswap/new.json?limit=10',
            status=429
        )
        
        posts = fetch_posts_json('hardwareswap', limit=10)
        assert posts is None
    
    @responses.activate
    def test_fetch_posts_json_forbidden(self):
        """Test handling of forbidden (403) response."""
        from bot import fetch_posts_json
        
        responses.add(
            responses.GET,
            'https://old.reddit.com/r/hardwareswap/new.json?limit=10',
            status=403
        )
        
        posts = fetch_posts_json('hardwareswap', limit=10)
        assert posts is None


class TestCredentialValidation:
    """Tests for credential validation in api.py (not bot.py)."""
    
    # These tests are NOT skipped since they test api.py which doesn't block
    pass


# Separate file for API credential tests that don't require bot.py import
