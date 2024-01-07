import praw
import time
import http.client
import urllib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import pickle
from concurrent.futures import ThreadPoolExecutor

# Load environment variables from .env file
load_dotenv()

class RedditMonitor:
    # Class variable to store processed submissions
    processed_submissions_file = 'processed_submissions.pkl'

    def __init__(self, subreddit, keywords, min_upvotes=None, max_notifications=5, time_threshold_minutes=60):
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.max_notifications = max_notifications
        self.time_threshold_minutes = time_threshold_minutes
        self.reddit = self.authenticate_reddit()
        self.load_processed_submissions()

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
        submission_time = datetime.fromtimestamp(timestamp)
        time_difference = current_time - submission_time
        return time_difference.total_seconds() <= (self.time_threshold_minutes * 60)

    def load_processed_submissions(self):
        try:
            with open(self.processed_submissions_file, 'rb') as file:
                self.processed_submissions = pickle.load(file)
        except FileNotFoundError:
            self.processed_submissions = set()

    def save_processed_submissions(self):
        with open(self.processed_submissions_file, 'wb') as file:
            pickle.dump(self.processed_submissions, file)

    def search_reddit_for_keywords(self):
        print(f"Searching '{self.subreddit}' subreddit for keywords...")
        subreddit_obj = self.reddit.subreddit(self.subreddit)
        notifications_count = 0

        try:
            for submission in subreddit_obj.new(limit=10):  # You can adjust the limit as needed
                submission_id = f"{self.subreddit}-{submission.id}"
                if submission_id in self.processed_submissions or not self.is_recent_submission(submission.created_utc):
                    print(f"Skipping duplicate or old post: {submission.title}")
                    continue

                message = f"Match found in '{self.subreddit}' subreddit:\n" \
                          f"Title: {submission.title}\n" \
                          f"URL: {submission.url}\n" \
                          f"Upvotes: {submission.score}\n" \
                          f"Author: {submission.author.name}"

                if all(keyword in submission.title.lower() for keyword in self.keywords) and \
                        (self.min_upvotes is None or submission.score >= self.min_upvotes):
                    print(message)
                    self.send_push_notification(message)
                    print('-' * 40)

                    self.processed_submissions.add(submission_id)
                    self.save_processed_submissions()  # Save the processed submissions to file
                    notifications_count += 1
                    if notifications_count >= self.max_notifications:
                        print("Reached the maximum number of notifications. Exiting...")
                        return  # Break out of the loop after reaching the maximum notifications

            print(f"Finished searching '{self.subreddit}' subreddit for keywords.")
        except Exception as e:
            print(f"Error during Reddit search for '{self.subreddit}':", e)

def main():
    # Example usage with parallel searching
    subreddits_to_search = [
        {'subreddit': 'hardwareswap', 'keywords': ['m50'], 'max_notifications': 3},
        # {'subreddit': 'frugalmalefashion', 'keywords': ['fjallraven'], 'min_upvotes': 20, 'max_notifications': 2},
        # {'subreddit': 'dogs', 'keywords': ['dogs', 'puppies'], 'min_upvotes': 30, 'max_notifications': 3},
    ]
    loopTime = 0
    while True:
        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(RedditMonitor(**params).search_reddit_for_keywords) for params in subreddits_to_search]
            # Wait for all tasks to complete
            for future in futures:
                future.result()

        # Add a delay before the next iteration
        iterationTime = 60  # ms
        print(f"Waiting for {iterationTime/60} minutes before the next iteration...")
        print(f"We have looped {loopTime} times")
        loopTime = loopTime + 1
        time.sleep(iterationTime)

if __name__ == "__main__":
    main()