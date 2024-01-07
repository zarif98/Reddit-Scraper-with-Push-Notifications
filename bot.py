import praw
import time
import http.client
import urllib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta


# Load environment variables from .env file
load_dotenv()

class RedditMonitor:
    def __init__(self, subreddit, keywords, min_upvotes=None, max_notifications=5, time_threshold_minutes=60, cleanup_interval_minutes=240):
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.max_notifications = max_notifications
        self.time_threshold_minutes = time_threshold_minutes
        self.cleanup_interval_minutes = cleanup_interval_minutes
        self.reddit = self.authenticate_reddit()
        self.processed_submissions = {}

    def authenticate_reddit(self):
        print("Authenticating Reddit...")
        return praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'),
                           client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                           user_agent=os.getenv('REDDIT_USER_AGENT'),
                           username=os.getenv('REDDIT_USERNAME'),
                           password=os.getenv('REDDIT_PASSWORD'))

    def send_push_notification(self, message):
        print("Sending Push Notification...")
        try:
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
                         urllib.parse.urlencode({
                             "token": os.getenv('PUSHOVER_APP_TOKEN'),
                             "user": os.getenv('PUSHOVER_USER_KEY'),
                             "message": message,
                         }), {"Content-type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            print("Pushover API response:", response.read().decode())
            conn.close()
        except Exception as e:
            print("Error sending Push Notification:", e)

    def is_recent_submission(self, timestamp):
        current_time = datetime.now()
        submission_time = datetime.fromtimestamp(timestamp)  # Use datetime.fromtimestamp instead of datetime.utcfromtimestamp
        time_difference = current_time - submission_time
        return time_difference.total_seconds() <= (self.time_threshold_minutes * 60)

    def cleanup_old_submissions(self):
        print("Performing cleanup of old submissions...")
        current_time = datetime.now(timezone.utc)
        # Calculate the cutoff time for entries to be considered old
        cutoff_time = current_time - timedelta(minutes=self.cleanup_interval_minutes)
        # Filter out entries older than the cutoff time
        self.processed_submissions = {title: timestamp for title, timestamp in self.processed_submissions.items()
                                      if datetime.utcfromtimestamp(timestamp) >= cutoff_time}
        print("Cleanup completed.")

    def search_reddit_for_keywords(self):
        print(f"Searching '{self.subreddit}' subreddit for keywords...")
        subreddit_obj = self.reddit.subreddit(self.subreddit)
        notifications_count = 0

        try:
            for submission in subreddit_obj.new(limit=10):  # You can adjust the limit as needed
                title = submission.title.lower()
                timestamp = submission.created_utc

                if title in self.processed_submissions or not self.is_recent_submission(timestamp):
                    print(f"Skipping duplicate or old post: {title}")
                message = f"Match found in '{self.subreddit}' subreddit:\n" \
                              f"Title: {submission.title}\n" \
                              f"URL: {submission.url}\n" \
                              f"Upvotes: {submission.score}\n" \
                              f"Author: {submission.author.name}"
                
                if all(keyword in title for keyword in self.keywords) and \
                        (self.min_upvotes is None or submission.score >= self.min_upvotes):
                    message = f"Match found in '{self.subreddit}' subreddit:\n" \
                              f"Title: {submission.title}\n" \
                              f"URL: {submission.url}\n" \
                              f"Upvotes: {submission.score}\n" \
                              f"Author: {submission.author.name}"

                    print(message)
                    self.send_push_notification(message)
                    print('-' * 40)

                    self.processed_submissions[title] = timestamp
                    notifications_count += 1
                    if notifications_count >= self.max_notifications:
                        print("Reached the maximum number of notifications. Exiting...")
                        return  # Break out of the loop after reaching the maximum notifications

            print(f"Finished searching '{self.subreddit}' subreddit for keywords.")
            # Perform cleanup after processing submissions
            self.cleanup_old_submissions()
        except Exception as e:
            print(f"Error during Reddit search for '{self.subreddit}':", e)

def main():
    # Example usage with parallel searching
    subreddits_to_search = [
        {'subreddit': 'hardwareswap', 'keywords': ['b450'], 'min_upvotes': 1, 'max_notifications': 3},
        {'subreddit': 'frugalmalefashion', 'keywords': ['fjallraven'], 'min_upvotes': 20, 'max_notifications': 2},
        {'subreddit': 'dogs', 'keywords': ['dogs', 'puppies'], 'min_upvotes': 30, 'max_notifications': 3},
    ]
    loopTime = 0
    while True:
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(RedditMonitor(**params).search_reddit_for_keywords) for params in subreddits_to_search]
            # Wait for all tasks to complete
            for future in futures:
                future.result()

        # Add a delay before the next iteration
        iterationTime = 60#ms
        print(f"Waiting for {iterationTime/60} minutes before the next iteration...")
        print(f"We have looped {loopTime} times")
        loopTime = loopTime + 1
        time.sleep(iterationTime)

if __name__ == "__main__":
    main()
