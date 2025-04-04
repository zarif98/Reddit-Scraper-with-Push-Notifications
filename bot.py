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
import logging


# --- Define paths for mounted data ---
DATA_DIR = '/data' # Base directory for mounted host data
CONFIG_FILE_PATH = os.path.join(DATA_DIR, 'search.json')
PROCESSED_SUBMISSIONS_FILE_PATH = os.path.join(DATA_DIR, 'processed_submissions.pkl')
# -------------------------------------

# Initialize colorama and logging
init(autoreset=True)

# Custom logging formatter with colors
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.colors = {
            logging.DEBUG: Fore.CYAN,
            logging.INFO: Fore.GREEN,
            logging.WARNING: Fore.YELLOW,
            logging.ERROR: Fore.RED,
            logging.CRITICAL: Fore.RED + Style.BRIGHT
        }

    def format(self, record):
        color = self.colors.get(record.levelno, Fore.WHITE)
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)

# Set up logging configuration
formatter = ColoredFormatter('%(asctime)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Load environment variables from .env file
load_dotenv()

# Check if all necessary environment variables are loaded
required_env_vars = ['PUSHOVER_APP_TOKEN', 'PUSHOVER_USER_KEY', 'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 'REDDIT_USER_AGENT', 'REDDIT_USERNAME', 'REDDIT_PASSWORD']
for var in required_env_vars:
    if os.getenv(var) is None:
        logging.error(f'Missing required environment variable: {var}')
        exit(1)

class RedditMonitor:
    processed_submissions_file = PROCESSED_SUBMISSIONS_FILE_PATH
    max_file_size = 5 * 1024 * 1024  # 5 MB

    def __init__(self, reddit, subreddit, keywords, min_upvotes=None):
        self.reddit = reddit
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.load_processed_submissions()

    def send_push_notification(self, message):
        logging.info("Sending Push Notification...")
        try:
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
                         urllib.parse.urlencode({
                             "token": os.getenv('PUSHOVER_APP_TOKEN'),
                             "user": os.getenv('PUSHOVER_USER_KEY'),
                             "message": message,
                         }), {"Content-type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            logging.info("Pushover API response: %s", response.read().decode())
            conn.close()
        except Exception as e:
            logging.error("Error sending Push Notification: %s", e)

    def load_processed_submissions(self):
        try:
            with open(self.processed_submissions_file, 'rb') as file:
                self.processed_submissions = pickle.load(file)
        except FileNotFoundError:
            self.processed_submissions = set()

    def save_processed_submissions(self):
        if os.path.exists(self.processed_submissions_file) and os.path.getsize(self.processed_submissions_file) > self.max_file_size:
            logging.info("Processed submissions file exceeded max size. Deleting and creating a new one.")
            os.remove(self.processed_submissions_file)
            self.processed_submissions = set()

        with open(self.processed_submissions_file, 'wb') as file:
            pickle.dump(self.processed_submissions, file)

    def send_error_notification(self, error_message):
        logging.error("Error occurred. Sending error notification...")
        try:
            conn = http.client.HTTPSConnection("api.pushover.net:443")
            conn.request("POST", "/1/messages.json",
                         urllib.parse.urlencode({
                             "token": os.getenv('PUSHOVER_APP_TOKEN'),
                             "user": os.getenv('PUSHOVER_USER_KEY'),
                             "message": f"Error in Reddit Scraper: {error_message}",
                         }), {"Content-type": "application/x-www-form-urlencoded"})
            response = conn.getresponse()
            logging.error("Pushover API response: %s", response.read().decode())
            conn.close()
        except Exception as e:
            logging.error("Error sending error notification: %s", e)

    def search_reddit_for_keywords(self):
        try:
            logging.info(f"Searching '{self.subreddit}' subreddit for keywords...")
            subreddit_obj = self.reddit.subreddit(self.subreddit)
            notifications_count = 0

            for submission in subreddit_obj.new(limit=10):  # Adjust the limit as needed
                submission_id = f"{self.subreddit}-{submission.id}"
                if submission_id in self.processed_submissions:
                    logging.info(f"Skipping duplicate post: {submission.title}")
                    continue

                message = f"Match found in '{self.subreddit}' subreddit:\n" \
                          f"Title: {submission.title}\n" \
                          f"URL: {submission.url}\n" \
                          f"Upvotes: {submission.score}\n" \
                          f"Permalink: https://www.reddit.com{submission.permalink}\n" \
                          ##f"Author: {submission.author.name}"

                if all(keyword in submission.title.lower() for keyword in self.keywords) and \
                        (self.min_upvotes is None or submission.score >= self.min_upvotes):
                    logging.info(message)
                    self.send_push_notification(message)
                    logging.info('-' * 40)

                    self.processed_submissions.add(submission_id)
                    self.save_processed_submissions()  # Save the processed submissions to file
                    notifications_count += 1

            logging.info(f"Finished searching '{self.subreddit}' subreddit for keywords.")
        except Exception as e:
            error_message = f"Error during Reddit search for '{self.subreddit}': {e}"
            logging.error(error_message)
            self.send_error_notification(error_message)

def authenticate_reddit():
    logging.info("Authenticating Reddit...")
    return praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'),
                       client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                       user_agent=os.getenv('REDDIT_USER_AGENT'),
                       username=os.getenv('REDDIT_USERNAME'),
                       password=os.getenv('REDDIT_PASSWORD'))

def main():
    reddit = authenticate_reddit()  # Authenticate Reddit once

    # Load parameters from config file using the absolute path
    logging.info(f"Loading configuration from: {CONFIG_FILE_PATH}")
    try:
        # Use the absolute path: /data/search.json
        with open(CONFIG_FILE_PATH, 'r') as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {CONFIG_FILE_PATH}")
        exit(1)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from configuration file: {CONFIG_FILE_PATH}")
        exit(1)

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
                    logging.error(error_message)
                    # Send an error notification for each subreddit search failure
                    RedditMonitor(reddit).send_error_notification(error_message)

        # Add a delay before the next iteration
        iterationTime = iteration_time_minutes * 60  # seconds
        logging.info(f"Waiting {iteration_time_minutes} minutes before the next iteration...")
        logging.info(f"We have looped {loopTime} times")
        loopTime += 1
        time.sleep(iterationTime)

if __name__ == "__main__":
    main()
