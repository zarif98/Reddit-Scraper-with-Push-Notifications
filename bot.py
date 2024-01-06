import praw
import time
from pushover import Client
from dotenv import load_dotenv
import os
from concurrent.futures import ThreadPoolExecutor

# Load environment variables from .env file
load_dotenv()

class RedditMonitor:
    def __init__(self, subreddit, keywords, min_upvotes=None, max_notifications=5):
        self.subreddit = subreddit
        self.keywords = keywords
        self.min_upvotes = min_upvotes
        self.max_notifications = max_notifications
        self.reddit = self.authenticate_reddit()

    def authenticate_reddit(self):
        return praw.Reddit(client_id=os.getenv('REDDIT_CLIENT_ID'),
                           client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                           user_agent=os.getenv('REDDIT_USER_AGENT'),
                           username=os.getenv('REDDIT_USERNAME'),
                           password=os.getenv('REDDIT_PASSWORD'))

    def send_pushover_notification(self, message):
        client = Client(os.getenv('PUSHOVER_API_TOKEN'), api_key=os.getenv('PUSHOVER_USER_KEY'))
        client.send_message(message)

    def search_reddit_for_keywords(self):
        subreddit_obj = self.reddit.subreddit(self.subreddit)
        notifications_count = 0
        
        for submission in subreddit_obj.new(limit=10):  # You can adjust the limit as needed
            title = submission.title.lower()
            if all(keyword in title for keyword in self.keywords) and \
               (self.min_upvotes is None or submission.score >= self.min_upvotes):
                message = f"Match found in '{self.subreddit}' subreddit:"
                message += f"\nTitle: {submission.title}"
                message += f"\nURL: {submission.url}"
                message += f"\nUpvotes: {submission.score}"
                message += f"\nAuthor: {submission.author.name}"
                
                print(message)
                self.send_pushover_notification(message)
                print('-' * 40)
                
                notifications_count += 1
                if notifications_count >= self.max_notifications:
                    return  # Break out of the loop after reaching the maximum notifications

def main():
    # Example usage with parallel searching
    subreddits_to_search = [
        {'subreddit': 'python', 'keywords': ['python', 'programming'], 'min_upvotes': 50, 'max_notifications': 3},
        {'subreddit': 'learnpython', 'keywords': ['learning', 'tutorial'], 'min_upvotes': 20, 'max_notifications': 2},
        {'subreddit': 'dogs', 'keywords': ['dogs', 'puppies'], 'min_upvotes': 30, 'max_notifications': 3},
    ]

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(RedditMonitor(**params).search_reddit_for_keywords) for params in subreddits_to_search]
        # Wait for all tasks to complete
        for future in futures:
            future.result()

if __name__ == "__main__":
    main()