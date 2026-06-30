"""Tests for thread comment monitoring functionality."""
import pytest
import responses
import json
from unittest.mock import MagicMock, patch, PropertyMock


def make_comment_response(comments):
    """Build a Reddit-style JSON response for a thread with given comments."""
    children = [
        {'kind': 't1', 'data': {
            'id': c['id'],
            'body': c['body'],
            'author': c.get('author', 'testuser'),
            'score': c.get('score', 1),
            'permalink': c.get('permalink', f"/r/test/comments/thread/{c['id']}/"),
        }}
        for c in comments
    ]
    return [
        {'data': {'children': []}},  # post data (index 0)
        {'data': {'children': children}},  # comments (index 1)
    ]


class TestFetchThreadCommentsJson:

    @responses.activate
    def test_returns_top_level_comments(self):
        from bot import fetch_thread_comments_json

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/comments/abc123.json',
            json=make_comment_response([
                {'id': 'c1', 'body': 'Size XS shirt $20', 'author': 'seller1'},
                {'id': 'c2', 'body': 'Size L pants $30', 'author': 'seller2'},
            ]),
            status=200,
        )

        comments = fetch_thread_comments_json('frugalmalefashion', 'abc123')
        assert comments is not None
        assert len(comments) == 2
        assert comments[0]['id'] == 'c1'
        assert comments[0]['body'] == 'Size XS shirt $20'

    @responses.activate
    def test_skips_non_comment_children(self):
        from bot import fetch_thread_comments_json

        data = make_comment_response([{'id': 'c1', 'body': 'XS shirt'}])
        # Add a 'more' object that should be skipped
        data[1]['data']['children'].append({'kind': 'more', 'data': {'children': ['x1', 'x2']}})

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/comments/abc123.json',
            json=data,
            status=200,
        )

        comments = fetch_thread_comments_json('frugalmalefashion', 'abc123')
        assert len(comments) == 1

    @responses.activate
    def test_returns_none_on_unexpected_structure(self):
        from bot import fetch_thread_comments_json

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/comments/abc123.json',
            json={'error': 'not found'},
            status=200,
        )

        result = fetch_thread_comments_json('frugalmalefashion', 'abc123')
        assert result is None

    @responses.activate
    def test_returns_none_on_http_error(self):
        from bot import fetch_thread_comments_json

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/comments/abc123.json',
            status=429,
        )

        result = fetch_thread_comments_json('frugalmalefashion', 'abc123')
        assert result is None

    @responses.activate
    def test_uses_limit_500_and_sort_new(self):
        from bot import fetch_thread_comments_json

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/comments/abc123.json',
            json=make_comment_response([]),
            status=200,
        )

        fetch_thread_comments_json('frugalmalefashion', 'abc123')
        assert 'limit=500' in responses.calls[0].request.url
        assert 'sort=new' in responses.calls[0].request.url


class TestProcessComment:

    def _make_monitor(self, keywords, keyword_logic='any', exclude_keywords=None,
                      author_includes=None, author_excludes=None):
        from bot import RedditMonitor
        monitor = RedditMonitor.__new__(RedditMonitor)
        monitor.subreddit = 'frugalmalefashion'
        monitor.keywords = keywords
        monitor.keyword_logic = keyword_logic
        monitor.exclude_keywords = exclude_keywords or []
        monitor.author_includes = author_includes or []
        monitor.author_excludes = author_excludes or []
        monitor.processed_submissions = set()
        monitor.send_push_notification = MagicMock()
        monitor.save_processed_submissions = MagicMock()
        return monitor

    def test_any_logic_matches_on_single_keyword(self):
        monitor = self._make_monitor(['xs', 'size s'], keyword_logic='any')
        result = monitor._process_comment('c1', 'Size XS Ralph Lauren polo $25', 'seller1', '/r/test/c1/')
        assert result is True
        monitor.send_push_notification.assert_called_once()

    def test_any_logic_no_match(self):
        monitor = self._make_monitor(['xs', 'size s'], keyword_logic='any')
        result = monitor._process_comment('c1', 'Size L jacket $40', 'seller1', '/r/test/c1/')
        assert result is False
        monitor.send_push_notification.assert_not_called()

    def test_all_logic_requires_all_keywords(self):
        monitor = self._make_monitor(['xs', 'polo'], keyword_logic='all')
        result = monitor._process_comment('c1', 'Size XS shirt $20', 'seller1', '/r/test/c1/')
        assert result is False

        result = monitor._process_comment('c2', 'Size XS polo $20', 'seller1', '/r/test/c2/')
        assert result is True

    def test_exclude_keywords_blocks_match(self):
        monitor = self._make_monitor(['xs'], exclude_keywords=['buying', 'wtb'])
        result = monitor._process_comment('c1', 'XS shirt - buying', 'user1', '/r/test/c1/')
        assert result is False

    def test_deduplication_skips_seen_comments(self):
        monitor = self._make_monitor(['xs'])
        monitor._process_comment('c1', 'Size XS shirt $20', 'seller1', '/r/test/c1/')
        monitor.send_push_notification.reset_mock()

        result = monitor._process_comment('c1', 'Size XS shirt $20', 'seller1', '/r/test/c1/')
        assert result is False
        monitor.send_push_notification.assert_not_called()

    def test_author_excludes_blocks_match(self):
        monitor = self._make_monitor(['xs'], author_excludes=['AutoModerator'])
        result = monitor._process_comment('c1', 'Size XS shirt $20', 'AutoModerator', '/r/test/c1/')
        assert result is False

    def test_author_includes_allows_only_listed_authors(self):
        monitor = self._make_monitor(['xs'], author_includes=['trustedseller'])
        result = monitor._process_comment('c1', 'Size XS shirt $20', 'randomuser', '/r/test/c1/')
        assert result is False

        result = monitor._process_comment('c2', 'Size XS shirt $20', 'trustedseller', '/r/test/c2/')
        assert result is True

    def test_notification_includes_excerpt_and_link(self):
        monitor = self._make_monitor(['xs'])
        monitor._process_comment('c1', 'Size XS Ralph Lauren polo $25', 'seller1', '/r/fmf/c1/')
        call_args = monitor.send_push_notification.call_args[0][0]
        assert 'seller1' in call_args
        assert 'XS' in call_args
        assert 'reddit.com' in call_args


class TestFindCurrentThread:

    @responses.activate
    def test_finds_thread_by_title_pattern_via_json(self):
        from bot import RedditMonitor

        # Clear cache
        RedditMonitor._thread_cache = {}
        RedditMonitor._using_json_fallback = True

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/new.json',
            json={'data': {'children': [
                {'data': {
                    'id': 'thread1',
                    'title': 'Official Weekly Buy/Sell/Trade Thread',
                    'permalink': '/r/frugalmalefashion/comments/thread1/official_weekly/',
                    'url': '', 'score': 1, 'domain': '', 'link_flair_text': '', 'author': 'mod',
                }},
                {'data': {
                    'id': 'post2',
                    'title': 'Cool jacket deal',
                    'permalink': '/r/frugalmalefashion/comments/post2/cool_jacket/',
                    'url': '', 'score': 5, 'domain': '', 'link_flair_text': '', 'author': 'user',
                }},
            ]}},
            status=200,
        )

        monitor = RedditMonitor.__new__(RedditMonitor)
        monitor.reddit = None
        monitor.subreddit = 'frugalmalefashion'
        monitor.thread_title_pattern = 'Buy/Sell/Trade'

        thread_id = monitor.find_current_thread()
        assert thread_id == 'thread1'

    @responses.activate
    def test_returns_none_when_no_matching_thread(self):
        from bot import RedditMonitor

        RedditMonitor._thread_cache = {}
        RedditMonitor._using_json_fallback = True

        responses.add(
            responses.GET,
            'https://old.reddit.com/r/frugalmalefashion/new.json',
            json={'data': {'children': []}},
            status=200,
        )

        monitor = RedditMonitor.__new__(RedditMonitor)
        monitor.reddit = None
        monitor.subreddit = 'frugalmalefashion'
        monitor.thread_title_pattern = 'Buy/Sell/Trade'

        thread_id = monitor.find_current_thread()
        assert thread_id is None

    def test_uses_cache_within_ttl(self):
        from bot import RedditMonitor
        import time

        RedditMonitor._thread_cache = {
            'frugalmalefashion-Buy/Sell/Trade': {
                'thread_id': 'cached_thread',
                'cached_at': time.time(),
            }
        }

        monitor = RedditMonitor.__new__(RedditMonitor)
        monitor.reddit = None
        monitor.subreddit = 'frugalmalefashion'
        monitor.thread_title_pattern = 'Buy/Sell/Trade'

        thread_id = monitor.find_current_thread()
        assert thread_id == 'cached_thread'
