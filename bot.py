import praw
import time
import http.client
import urllib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os
import pickle
from concurrent.futures import ThreadPoolExecutor
from colorama import init, Fore, Style
import json

# Initialize colorama
init(autoreset=True)

# Load environment variables from .env file
load_dotenv()

class RedditMonitor:
    processed_submissions_file = 'processed_submissions.pkl'

    def __init__(self, reddit, subreddit, keywords, min_upvotes=None):
        self.reddit = reddit
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.load_processed_submissions()

    def send_push_notification(self, message):
        print(Fore.CYAN + "Sending Push Notification..." + Style.RESET_ALL)
        try:
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
                         urllib.parse.urlencode({
                             "token": os.getenv('PUSHOVER_APP_TOKEN'),
                             "user": os.getenv('PUSHOVER_USER_KEY'),
                             "message": message,
                         }), {"Content-type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            print(Fore.CYAN + "Pushover API response:" + Style.RESET_ALL, response.read().decode())
            conn.close()
        except Exception as e:
            print(Fore.RED + "Error sending Push Notification:" + Style.RESET_ALL, e)

    def load_processed_submissions(self):
        try:
            with open(self.processed_submissions_file, 'rb') as file:
                self.processed_submissions = pickle.load(file)
        except FileNotFoundError:
            self.processed_submissions = set()

    def save_processed_submissions(self):
        with open(self.processed_submissions_file, 'wb') as file:
            pickle.dump(self.processed_submissions, file)

    def send_error_notification(self, error_message):
        print(Fore.RED + "Error occurred. Sending error notification..." + Style.RESET_ALL)
        try:
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
                         urllib.parse.urlencode({
                             "token": os.getenv('PUSHOVER_APP_TOKEN'),
                             "user": os.getenv('PUSHOVER_USER_KEY'),
                             "message": f"Error in Reddit Scraper: {error_message}",
                         }), {"Content-type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            print(Fore.RED + "Pushover API response:" + Style.RESET_ALL, response.read().decode())
            conn.close()
        except Exception as e:
            print(Fore.RED + "Error sending error notification:" + Style.RESET_ALL, e)

    def search_reddit_for_keywords(self):
        try:
            print(Fore.YELLOW + f"Searching '{self.subreddit}' subreddit for keywords..." + Style.RESET_ALL)
            subreddit_obj = self.reddit.subreddit(self.subreddit)
            notifications_count = 0

            for submission in subreddit_obj.new(limit=10):  # You can adjust the limit as needed
                submission_id = f"{self.subreddit}-{submission.id}"
                if submission_id in self.processed_submissions:
                    print(Fore.YELLOW + f"Skipping duplicate post: {submission.title}" + Style.RESET_ALL)
                    continue

                message = f"Match found in '{self.subreddit}' subreddit:\n" \
                          f"Title: {submission.title}\n" \
                          f"URL: {submission.url}\n" \
                          f"Upvotes: {submission.score}\n" \
                          f"Author: {submission.author.name}"

                if all(keyword in submission.title.lower() for keyword in self.keywords) and \
                        (self.min_upvotes is None or submission.score >= self.min_upvotes):
                    print(Fore.GREEN + message + Style.RESET_ALL)
                    self.send_push_notification(message)
                    print(Fore.YELLOW + '-' * 40 + Style.RESET_ALL)

                    self.processed_submissions.add(submission_id)
                    self.save_processed_submissions()  # Save the processed submissions to file
                    notifications_count += 1

            print(Fore.YELLOW + f"Finished searching '{self.subreddit}' subreddit for keywords." + Style.RESET_ALL)
        except Exception as e:
            error_message = f"Error during Reddit search for '{self.subreddit}': {e}"
            print(Fore.RED + error_message + Style.RESET_ALL)
            self.send_error_notification(error_message)

def authenticate_reddit():
    print(Fore.GREEN + "Authenticating Reddit..." + Style.RESET_ALL)
    return praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'),
                       client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                       user_agent=os.getenv('REDDIT_USER_AGENT'),
                       username=os.getenv('REDDIT_USERNAME'),
                       password=os.getenv('REDDIT_PASSWORD'))

def main():
    reddit = authenticate_reddit()  # Authenticate Reddit once

    # Load parameters from config.json
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)

    subreddits_to_search = config.get('subreddits_to_search', [])
    iteration_time_minutes = config.get('iteration_time_minutes', 5)

    loopTime = 0
    while True:
        with ThreadPoolExecutor() as executor:
            # Use list comprehension to store futures and handle exceptions separately
            futures = [executor.submit(RedditMonitor(reddit, **params).search_reddit_for_keywords) for params in subreddits_to_search]

            # Handle exceptions from each future separately
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    error_message = f"Error during subreddit search: {e}"
                    print(Fore.RED + error_message + Style.RESET_ALL)
                    # Send an error notification for each subreddit search failure
                    RedditMonitor(reddit).send_error_notification(error_message)

        # Add a delay before the next iteration
        iterationTime = iteration_time_minutes * 60  # seconds
        print(Fore.MAGENTA + f"Waiting {iteration_time_minutes} minutes before the next iteration..." + Style.RESET_ALL)
        print(Fore.MAGENTA + f"We have looped {loopTime} times" + Style.RESET_ALL)
        loopTime += 1
        time.sleep(iterationTime)

if __name__ == "__main__":
    main()
