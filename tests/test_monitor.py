"""Tests for post filtering in RedditMonitor._process_post (reddit_scraper.monitor)."""
from unittest.mock import MagicMock

from reddit_scraper.monitor import RedditMonitor


def make_monitor(keywords=('4090',), **overrides):
    """Build a RedditMonitor without __init__ (no file/network), with mocked side effects."""
    m = RedditMonitor.__new__(RedditMonitor)
    m.subreddit = 'hardwareswap'
    m.keywords = list(keywords)
    m.exclude_keywords = overrides.get('exclude_keywords', [])
    m.min_upvotes = overrides.get('min_upvotes', None)
    m.domain_contains = overrides.get('domain_contains', [])
    m.domain_excludes = overrides.get('domain_excludes', [])
    m.flair_contains = overrides.get('flair_contains', [])
    m.author_includes = overrides.get('author_includes', [])
    m.author_excludes = overrides.get('author_excludes', [])
    m.processed_submissions = set()
    m.send_push_notification = MagicMock()
    m.save_processed_submissions = MagicMock()
    return m


def process(m, *, post_id='p1', title='RTX 4090 for sale', score=50,
            domain='ebay.com', flair='SELLING', author='seller1'):
    return m._process_post(post_id=post_id, title=title, url='http://x', score=score,
                           permalink='/r/x/p1/', domain=domain, flair=flair, author=author)


class TestProcessPost:

    def test_basic_match_notifies(self):
        m = make_monitor()
        assert process(m) is True
        m.send_push_notification.assert_called_once()

    def test_requires_all_keywords(self):
        m = make_monitor(keywords=('4090', 'founders'))
        assert process(m, title='RTX 4090 for sale') is False
        assert process(m, post_id='p2', title='RTX 4090 founders edition') is True

    def test_exclude_keyword_blocks(self):
        m = make_monitor(exclude_keywords=['wanted'])
        assert process(m, title='RTX 4090 wanted') is False

    def test_min_upvotes_blocks_low_score(self):
        m = make_monitor(min_upvotes=100)
        assert process(m, score=50) is False
        assert process(m, post_id='p2', score=150) is True

    def test_domain_contains_requires_match(self):
        m = make_monitor(domain_contains=['amazon.com'])
        assert process(m, domain='ebay.com') is False
        assert process(m, post_id='p2', domain='amazon.com') is True

    def test_domain_excludes_blocks(self):
        m = make_monitor(domain_excludes=['ebay.com'])
        assert process(m, domain='ebay.com') is False

    def test_flair_contains_requires_match(self):
        m = make_monitor(flair_contains=['selling'])
        assert process(m, flair='BUYING') is False
        assert process(m, post_id='p2', flair='SELLING') is True

    def test_author_includes_allows_only_listed(self):
        m = make_monitor(author_includes=['trusted'])
        assert process(m, author='random') is False
        assert process(m, post_id='p2', author='trusted') is True

    def test_author_excludes_blocks(self):
        m = make_monitor(author_excludes=['automoderator'])
        assert process(m, author='AutoModerator') is False

    def test_deduplicates_processed_posts(self):
        m = make_monitor()
        assert process(m, post_id='dup') is True
        m.send_push_notification.reset_mock()
        assert process(m, post_id='dup') is False
        m.send_push_notification.assert_not_called()
