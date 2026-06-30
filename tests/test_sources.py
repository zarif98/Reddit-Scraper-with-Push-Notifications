"""Tests for the data-source pathways and dispatcher (reddit_scraper.sources)."""
import pytest
import responses

from reddit_scraper import sources, config


@pytest.fixture(autouse=True)
def reset_source_state():
    """Source state is module-global; reset it (and disable RSS throttling/caching) per test."""
    sources._source_cooldown_until.clear()
    sources._source_failures.clear()
    sources._fetch_cache.clear()
    sources._fetch_key_locks.clear()
    sources._active_source = None
    sources._LAST_FETCH_SUCCESS_TS = None
    sources._auth_error_notified = False
    sources._rss_last_request[0] = 0.0
    sources.RSS_MIN_INTERVAL = 0
    sources.FETCH_CACHE_TTL = 0  # disable caching by default; coalescing tests opt back in
    config.set_source_order(None)  # back to default oauth -> json -> rss
    yield


POST_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <author><name>/u/dealhunter</name></author>
  <category term="Expired" label="r/gamedeals"/>
  <content type="html">&lt;a href="https://store.example.com/x"&gt;[link]&lt;/a&gt;</content>
  <id>t3_abc123</id>
  <link href="https://www.reddit.com/r/gamedeals/comments/abc123/red_dead_redemption_75_off/"/>
  <updated>2026-06-29T19:00:00+00:00</updated>
  <title>Red Dead Redemption 75% off</title>
 </entry>
</feed>'''

COMMENT_FEED = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <id>t3_abc123</id><title>the post itself</title>
  <link href="https://www.reddit.com/r/x/comments/abc123/"/>
 </entry>
 <entry>
  <author><name>/u/seller</name></author>
  <content type="html">&lt;p&gt;WTS shirt size &lt;b&gt;Small&lt;/b&gt; $20&lt;/p&gt;</content>
  <id>t1_def456</id>
  <link href="https://www.reddit.com/r/x/comments/abc123/_/def456/"/>
  <title>comment title</title>
 </entry>
</feed>'''


class TestFetchPostsRss:

    @responses.activate
    def test_parses_and_normalizes_fields(self):
        responses.add(responses.GET, 'https://www.reddit.com/r/gamedeals/new/.rss',
                      body=POST_FEED, status=200)
        posts = sources.fetch_posts_rss('gamedeals', limit=10)

        assert len(posts) == 1
        p = posts[0]
        assert p['id'] == 'abc123'                       # t3_ prefix stripped
        assert p['title'] == 'Red Dead Redemption 75% off'
        assert p['author'] == 'dealhunter'               # /u/ stripped
        assert p['link_flair_text'] == 'Expired'         # from <category term=...>
        assert p['permalink'] == '/r/gamedeals/comments/abc123/red_dead_redemption_75_off/'
        assert p['score'] == 0                            # not exposed via RSS
        assert p['domain'] == ''                          # not exposed via RSS

    @responses.activate
    def test_raises_on_403(self):
        responses.add(responses.GET, 'https://www.reddit.com/r/gamedeals/new/.rss', status=403)
        with pytest.raises(RuntimeError):
            sources.fetch_posts_rss('gamedeals')

    @responses.activate
    def test_raises_on_429(self):
        responses.add(responses.GET, 'https://www.reddit.com/r/gamedeals/new/.rss', status=429)
        with pytest.raises(RuntimeError):
            sources.fetch_posts_rss('gamedeals')


class TestFetchThreadCommentsRss:

    @responses.activate
    def test_filters_post_entry_and_strips_html(self):
        responses.add(responses.GET, 'https://www.reddit.com/r/x/comments/abc123/.rss',
                      body=COMMENT_FEED, status=200)
        comments = sources.fetch_thread_comments_rss('x', 'abc123')

        assert len(comments) == 1                          # the t3_ post entry is skipped
        c = comments[0]
        assert c['id'] == 'def456'
        assert c['author'] == 'seller'
        assert c['body'] == 'WTS shirt size Small $20'      # HTML tags stripped


def _post():
    return [{'id': '1', 'title': 't', 'url': '', 'score': 0,
             'permalink': '/p', 'domain': '', 'link_flair_text': '', 'author': 'a'}]


def _raises(*a, **k):
    raise RuntimeError("blocked")


class TestFetchPostsDispatcher:
    """Tests set source order explicitly so they don't depend on the production default."""

    def test_skips_oauth_when_no_reddit_and_uses_next_source(self, monkeypatch):
        config.set_source_order(['oauth', 'json', 'rss'])
        monkeypatch.setattr(sources, 'fetch_posts_json', lambda sub, lim: _post())
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: _post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'json'          # oauth skipped (no reddit), json is next
        assert sources._active_source == 'json'

    def test_falls_through_on_failure_and_cools_down(self, monkeypatch):
        config.set_source_order(['json', 'rss'])
        monkeypatch.setattr(sources, 'fetch_posts_json', _raises)
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: [])
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'rss'
        assert posts == []
        assert not sources._source_available('json')       # failed source on cooldown

    def test_returns_none_when_all_sources_fail(self, monkeypatch):
        config.set_source_order(['json', 'rss'])
        monkeypatch.setattr(sources, 'fetch_posts_json', _raises)
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: None)
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert posts is None and source is None

    def test_cooldown_source_is_skipped(self, monkeypatch):
        config.set_source_order(['json', 'rss'])
        sources._mark_source_down('json', 300)
        called = {'json': False}

        def json_fetch(sub, lim):
            called['json'] = True
            return _post()
        monkeypatch.setattr(sources, 'fetch_posts_json', json_fetch)
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: _post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'rss'           # json skipped due to cooldown
        assert called['json'] is False

    def test_oauth_success_sets_active_source_and_records_success(self, monkeypatch):
        monkeypatch.setattr(sources, '_fetch_posts_oauth', lambda r, sub, lim: _post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=object())
        assert source == 'oauth'
        assert sources._active_source == 'oauth'
        assert sources._LAST_FETCH_SUCCESS_TS is not None


class TestAuthErrorNotificationGuard:

    def test_concurrent_401s_notify_only_once(self, monkeypatch):
        """6 monitors hitting the same OAuth 401 in parallel must produce one alert."""
        from concurrent.futures import ThreadPoolExecutor

        monkeypatch.setattr(sources, '_fetch_posts_oauth',
                            lambda reddit, sub, lim: (_ for _ in ()).throw(RuntimeError("received 401 HTTP response")))
        # next source serves so the chain completes (stub both to avoid the network)
        monkeypatch.setattr(sources, 'fetch_posts_json', lambda sub, lim: _post())
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: _post())

        calls = []
        monkeypatch.setattr(sources.notifications, 'notify_error', lambda msg: calls.append(msg))

        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(lambda i: sources.fetch_posts('gamedeals', 10, reddit=object()), range(6)))

        assert len(calls) == 1


class TestCoalescing:

    def test_duplicate_subreddit_shares_one_request(self, monkeypatch):
        sources.FETCH_CACHE_TTL = 90
        calls = {'n': 0}

        def served(sub, lim):
            calls['n'] += 1
            return _post()
        monkeypatch.setattr(sources, 'fetch_posts_json', served)

        r1 = sources.fetch_posts('frugalmalefashion', 10, None)
        r2 = sources.fetch_posts('frugalmalefashion', 10, None)
        assert calls['n'] == 1          # second served from cache
        assert r1 == r2

    def test_concurrent_duplicates_coalesce_to_one(self, monkeypatch):
        from concurrent.futures import ThreadPoolExecutor
        import time
        sources.FETCH_CACHE_TTL = 90
        calls = {'n': 0}

        def served(sub, lim):
            calls['n'] += 1
            time.sleep(0.05)            # widen the race window
            return _post()
        monkeypatch.setattr(sources, 'fetch_posts_json', served)

        with ThreadPoolExecutor(max_workers=5) as ex:
            list(ex.map(lambda i: sources.fetch_posts('frugalmalefashion', 10, None), range(5)))
        assert calls['n'] == 1

    def test_different_subreddits_not_shared(self, monkeypatch):
        sources.FETCH_CACHE_TTL = 90
        calls = {'n': 0}
        monkeypatch.setattr(sources, 'fetch_posts_json',
                            lambda sub, lim: (calls.__setitem__('n', calls['n'] + 1) or _post()))
        sources.fetch_posts('gamedeals', 10, None)
        sources.fetch_posts('apphookup', 10, None)
        assert calls['n'] == 2

    def test_whole_chain_is_coalesced(self, monkeypatch):
        """Coalescing wraps the entire chain, so every source (incl. JSON) fires once per burst."""
        sources.FETCH_CACHE_TTL = 90
        config.set_source_order(['json', 'rss'])
        json_calls = {'n': 0}
        rss_calls = {'n': 0}
        monkeypatch.setattr(sources, 'fetch_posts_json',
                            lambda sub, lim: (json_calls.__setitem__('n', json_calls['n'] + 1) or _raises()))
        monkeypatch.setattr(sources, 'fetch_posts_rss',
                            lambda sub, lim: (rss_calls.__setitem__('n', rss_calls['n'] + 1) or _post()))
        sources.fetch_posts('gamedeals', 10, None)
        sources.fetch_posts('gamedeals', 10, None)
        assert json_calls['n'] == 1 and rss_calls['n'] == 1   # whole chain ran once, then cached


class TestBackoff:

    def test_exponential_backoff_on_consecutive_failures(self):
        import time
        sources._mark_source_down('rss')                       # 1st: base (300s)
        first = sources._source_cooldown_until['rss'] - time.time()
        sources._mark_source_down('rss')                       # 2nd: 2x (600s)
        second = sources._source_cooldown_until['rss'] - time.time()
        assert 290 < first <= sources.SOURCE_COOLDOWN_SECONDS
        assert second > first * 1.5                            # roughly doubled

    def test_success_resets_backoff(self):
        sources._mark_source_down('rss')
        sources._mark_source_down('rss')
        assert sources._source_failures['rss'] == 2
        sources._note_source_success('rss')
        assert sources._source_failures['rss'] == 0

    def test_backoff_capped(self, monkeypatch):
        monkeypatch.setattr(sources, 'SOURCE_COOLDOWN_MAX', 1000)
        import time
        for _ in range(10):
            sources._mark_source_down('rss')
        assert sources._source_cooldown_until['rss'] - time.time() <= 1000

    def test_explicit_seconds_does_not_increment_failures(self):
        sources._mark_source_down('rss', 50)
        assert sources._source_failures.get('rss', 0) == 0
