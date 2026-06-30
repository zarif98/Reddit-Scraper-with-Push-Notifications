"""Tests for the data-source pathways and dispatcher (reddit_scraper.sources)."""
import pytest
import responses

from reddit_scraper import sources, config


@pytest.fixture(autouse=True)
def reset_source_state():
    """Source state is module-global; reset it (and disable RSS throttling) per test."""
    sources._source_cooldown_until.clear()
    sources._active_source = None
    sources._LAST_FETCH_SUCCESS_TS = None
    sources._auth_error_notified = False
    sources._rss_last_request[0] = 0.0
    sources.RSS_MIN_INTERVAL = 0
    config.set_source_order(None)  # back to default oauth -> rss -> json
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


class TestFetchPostsDispatcher:

    def _post(self):
        return [{'id': '1', 'title': 't', 'url': '', 'score': 0,
                 'permalink': '/p', 'domain': '', 'link_flair_text': '', 'author': 'a'}]

    def test_skips_oauth_when_no_reddit_and_uses_rss(self, monkeypatch):
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: self._post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'rss'
        assert len(posts) == 1
        assert sources._active_source == 'rss'

    def test_falls_through_to_json_and_cools_down_failed_source(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("RSS blocked (429)")
        monkeypatch.setattr(sources, 'fetch_posts_rss', boom)
        monkeypatch.setattr(sources, 'fetch_posts_json', lambda sub, lim: [])
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'json'
        assert posts == []
        assert not sources._source_available('rss')        # rss is on cooldown

    def test_returns_none_when_all_sources_fail(self, monkeypatch):
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: (_ for _ in ()).throw(RuntimeError()))
        monkeypatch.setattr(sources, 'fetch_posts_json', lambda sub, lim: None)
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert posts is None and source is None

    def test_cooldown_source_is_skipped(self, monkeypatch):
        sources._mark_source_down('rss', 300)
        called = {'rss': False}

        def rss(sub, lim):
            called['rss'] = True
            return self._post()
        monkeypatch.setattr(sources, 'fetch_posts_rss', rss)
        monkeypatch.setattr(sources, 'fetch_posts_json', lambda sub, lim: self._post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=None)
        assert source == 'json'          # rss skipped due to cooldown
        assert called['rss'] is False

    def test_oauth_success_sets_active_source_and_records_success(self, monkeypatch):
        monkeypatch.setattr(sources, '_fetch_posts_oauth', lambda r, sub, lim: self._post())
        posts, source = sources.fetch_posts('gamedeals', 10, reddit=object())
        assert source == 'oauth'
        assert sources._active_source == 'oauth'
        assert sources._LAST_FETCH_SUCCESS_TS is not None


class TestAuthErrorNotificationGuard:

    def test_concurrent_401s_notify_only_once(self, monkeypatch):
        """6 monitors hitting the same OAuth 401 in parallel must produce one alert."""
        from concurrent.futures import ThreadPoolExecutor

        def oauth_401(reddit, sub, lim):
            raise RuntimeError("received 401 HTTP response")
        monkeypatch.setattr(sources, '_fetch_posts_oauth', oauth_401)
        monkeypatch.setattr(sources, 'fetch_posts_rss', lambda sub, lim: self._post())

        calls = []
        monkeypatch.setattr(sources.notifications, 'notify_error', lambda msg: calls.append(msg))

        with ThreadPoolExecutor(max_workers=6) as ex:
            list(ex.map(lambda i: sources.fetch_posts('gamedeals', 10, reddit=object()), range(6)))

        assert len(calls) == 1

    def _post(self):
        return [{'id': '1', 'title': 't', 'url': '', 'score': 0,
                 'permalink': '/p', 'domain': '', 'link_flair_text': '', 'author': 'a'}]
