"""RedditMonitor: evaluates a subreddit (or BST thread) against keyword/filter rules."""
import os
import time
import pickle
import logging

from . import config, credentials, notifications, sources


class RedditMonitor:
    max_file_size = 5 * 1024 * 1024  # 5 MB
    # Kept for backwards-compat with tests; the active source is now driven by the
    # source chain in `sources`, not this flag.
    _using_json_fallback = False
    _thread_cache = {}  # subreddit+pattern -> {thread_id, cached_at}
    THREAD_CACHE_TTL = 3600  # refresh cached thread ID every hour

    def __init__(self, reddit, subreddit, keywords, min_upvotes=None, exclude_keywords=None,
                 domain_contains=None, domain_excludes=None, flair_contains=None,
                 author_includes=None, author_excludes=None, **kwargs):
        self.reddit = reddit
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.exclude_keywords = exclude_keywords or []
        self.domain_contains = domain_contains or []
        self.domain_excludes = domain_excludes or []
        self.flair_contains = flair_contains or []
        self.author_includes = author_includes or []
        self.author_excludes = author_excludes or []
        self.monitor_type = kwargs.get('monitor_type', 'posts')
        self.thread_title_pattern = kwargs.get('thread_title_pattern', 'Buy/Sell/Trade')
        self.keyword_logic = kwargs.get('keyword_logic', 'any')
        self.load_processed_submissions()

    def run(self):
        """Dispatch to the correct monitor method based on monitor_type."""
        if self.monitor_type == 'thread_comments':
            self.search_thread_comments()
        else:
            self.search_reddit_for_keywords()

    def send_push_notification(self, message, title=None):
        """Send notification via Apprise to all configured services."""
        urls = credentials.CREDENTIALS.get('notification_urls', []) if credentials.CREDENTIALS else []
        if not urls:
            logging.debug("No notification services configured, skipping notification")
            return

        logging.info(f"Sending notification to {len(urls)} service(s)...")
        result = notifications.dispatch(message, title or f"Reddit Alert: r/{self.subreddit}")
        if result:
            logging.info("✅ Notification sent successfully")
        else:
            logging.warning("⚠️ Some notifications may have failed")

    def send_error_notification(self, error_message):
        """Send error notification via Apprise to all configured services."""
        notifications.notify_error(error_message)

    @property
    def processed_submissions_file(self):
        return config.get_processed_submissions_path()

    def load_processed_submissions(self):
        try:
            with open(self.processed_submissions_file, 'rb') as file:
                self.processed_submissions = pickle.load(file)
        except FileNotFoundError:
            self.processed_submissions = set()

    def save_processed_submissions(self):
        path = self.processed_submissions_file
        if os.path.exists(path) and os.path.getsize(path) > self.max_file_size:
            logging.info("Processed submissions file exceeded max size. Deleting and creating a new one.")
            os.remove(path)
            self.processed_submissions = set()

        with open(path, 'wb') as file:
            pickle.dump(self.processed_submissions, file)

    def find_current_thread(self):
        """Find the thread ID of the current weekly megathread, with 1-hour caching."""
        cache_key = f"{self.subreddit}-{self.thread_title_pattern}"
        cached = RedditMonitor._thread_cache.get(cache_key)
        if cached and (time.time() - cached['cached_at']) < RedditMonitor.THREAD_CACHE_TTL:
            return cached['thread_id']

        thread_id = None
        pattern = self.thread_title_pattern.lower()

        # Stickied posts are the most reliable signal, but only PRAW exposes them.
        if self.reddit and sources._source_available('oauth'):
            try:
                sub = self.reddit.subreddit(self.subreddit)
                for slot in [1, 2]:
                    try:
                        sticky = sub.sticky(number=slot)
                        if pattern in sticky.title.lower():
                            thread_id = sticky.id
                            break
                    except Exception:
                        pass
            except Exception as e:
                logging.warning(f"PRAW error finding sticky BST thread: {e}")

        # Otherwise scan recent posts via the source chain (oauth -> rss -> json).
        if not thread_id:
            posts, _ = sources.fetch_posts(self.subreddit, 25, self.reddit)
            for post in (posts or []):
                if pattern in (post['title'] or '').lower():
                    if post.get('id'):
                        thread_id = post['id']
                    else:
                        parts = post['permalink'].strip('/').split('/')
                        if 'comments' in parts:
                            thread_id = parts[parts.index('comments') + 1]
                    break

        if thread_id:
            RedditMonitor._thread_cache[cache_key] = {'thread_id': thread_id, 'cached_at': time.time()}
            logging.info(f"Thread located: {thread_id}")
        else:
            logging.warning(f"Could not find thread matching '{self.thread_title_pattern}' in r/{self.subreddit}")

        return thread_id

    def search_thread_comments(self):
        """Scan a pinned/recurring thread's comments for keyword matches."""
        thread_id = self.find_current_thread()
        if not thread_id:
            return

        logging.info(f"Scanning thread {thread_id} comments in r/{self.subreddit}...")
        comments = sources.fetch_thread_comments(self.subreddit, thread_id, self.reddit)
        if comments is None:
            return

        for comment in comments:
            self._process_comment(
                comment_id=comment['id'],
                body=comment['body'],
                author=comment['author'],
                permalink=comment['permalink'],
            )
        logging.info(f"Finished scanning thread comments in r/{self.subreddit}.")

    def _process_comment(self, comment_id, body, author, permalink):
        """Check a BST comment against keyword filters and notify on match."""
        submission_id = f"{self.subreddit}-comment-{comment_id}"
        if submission_id in self.processed_submissions:
            return False

        body_lower = body.lower()

        if self.keyword_logic == 'any':
            has_keywords = any(kw.lower() in body_lower for kw in self.keywords)
        else:
            has_keywords = all(kw.lower() in body_lower for kw in self.keywords)

        has_excluded = any(kw.lower() in body_lower for kw in self.exclude_keywords)
        author_lower = author.lower()
        meets_author_includes = not self.author_includes or author_lower in [a.lower() for a in self.author_includes]
        meets_author_excludes = author_lower not in [a.lower() for a in self.author_excludes]

        if has_keywords and not has_excluded and meets_author_includes and meets_author_excludes:
            excerpt = body[:300] + '...' if len(body) > 300 else body
            message = (
                f"BST listing match in r/{self.subreddit}!\n"
                f"u/{author}:\n{excerpt}\n"
                f"Link: https://www.reddit.com{permalink}"
            )
            self.send_push_notification(message, title="FMF BST Match")
            logging.info(f"BST match: u/{author} | {body[:80]}...")
            self.processed_submissions.add(submission_id)
            self.save_processed_submissions()
            return True

        return False

    def search_reddit_for_keywords(self):
        """Search a subreddit for keywords, fetching posts through the configured source chain."""
        logging.info(f"Searching '{self.subreddit}' subreddit for keywords...")
        posts, source = sources.fetch_posts(self.subreddit, 10, self.reddit)

        if posts is None:
            logging.error(f"Failed to fetch posts for '{self.subreddit}' from all sources")
            return

        for post in posts:
            self._process_post(
                post_id=post['id'],
                title=post['title'],
                url=post['url'],
                score=post['score'],
                permalink=post['permalink'],
                domain=post['domain'],
                flair=post['link_flair_text'] or '',
                author=post['author']
            )

        logging.info(f"Finished searching '{self.subreddit}' subreddit (source: {source}).")

    def _process_post(self, post_id, title, url, score, permalink, domain, flair, author):
        """Process a single post and send notification if it matches filters."""
        submission_id = f"{self.subreddit}-{post_id}"
        if submission_id in self.processed_submissions:
            logging.debug(f"Skipping duplicate post: {title}")
            return False

        message = f"Match found in '{self.subreddit}' subreddit:\n" \
                  f"Title: {title}\n" \
                  f"URL: {url}\n" \
                  f"Upvotes: {score}\n" \
                  f"Permalink: https://www.reddit.com{permalink}\n"

        # Check filters
        title_lower = title.lower()
        has_all_keywords = all(keyword in title_lower for keyword in self.keywords)
        has_excluded = any(keyword in title_lower for keyword in self.exclude_keywords)
        meets_upvotes = self.min_upvotes is None or score >= self.min_upvotes

        # Domain filters
        submission_domain = domain.lower()
        meets_domain_contains = not self.domain_contains or any(d in submission_domain for d in self.domain_contains)
        meets_domain_excludes = not any(d in submission_domain for d in self.domain_excludes)

        # Flair filter
        submission_flair = flair.lower()
        meets_flair = not self.flair_contains or any(f.lower() in submission_flair for f in self.flair_contains)

        # Author filters
        author_name = author.lower()
        meets_author_includes = not self.author_includes or author_name in [a.lower() for a in self.author_includes]
        meets_author_excludes = author_name not in [a.lower() for a in self.author_excludes]

        if (has_all_keywords and not has_excluded and meets_upvotes and
                meets_domain_contains and meets_domain_excludes and
                meets_flair and meets_author_includes and meets_author_excludes):
            logging.info(message)
            self.send_push_notification(message)
            logging.info('-' * 40)

            self.processed_submissions.add(submission_id)
            self.save_processed_submissions()
            return True

        return False
