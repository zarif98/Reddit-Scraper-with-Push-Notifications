# Reddit Data API Application - Reddit Monitor

## Executive Summary

**Project Name:** Reddit Monitor with Push Notifications  
**Developer:** Zarif  
**GitHub Repository:** [Reddit-Scraper-with-Push-Notifications](https://github.com/zarif98/Reddit-Scraper-with-Push-Notifications)  
**Application Type:** Personal/Non-Commercial Self-Hosted Tool  
**License:** MIT License (Open Source)

---

## Application Overview

Reddit Monitor is an **open-source, self-hosted personal notification tool** that helps individual users stay informed about new posts in their favorite subreddits. When posts matching user-defined keywords appear, the application sends push notifications to the user's personal devices.

### Core Functionality

The application performs a simple, focused function:
- **Search**: Queries subreddits for new posts using Reddit's public API
- **Filter**: Matches posts against user-defined keywords
- **Notify**: Sends push notifications to the user's personal devices

### Key Technical Details

- **API Library**: Uses [PRAW (Python Reddit API Wrapper)](https://praw.readthedocs.io/) - Reddit's officially recommended Python library
- **Authentication**: OAuth2 "script" type application (for personal use)
- **API Access Pattern**: Read-only access to public subreddit posts
- **Rate Limiting**: Fully respects Reddit's API rate limits (PRAW handles this automatically)

---

## Responsible Builder Policy Compliance

### ✅ Transparency & Honest Intent

**What the application does:**
- Monitors user-specified public subreddits for new posts
- Filters posts based on keywords defined by the user
- Sends notifications to the user's own devices
- Tracks previously seen posts to avoid duplicate notifications

**What the application does NOT do:**
- ❌ Does NOT scrape or bulk download Reddit data
- ❌ Does NOT store or archive Reddit content
- ❌ Does NOT share, sell, or redistribute any Reddit data
- ❌ Does NOT train AI/ML models on Reddit data
- ❌ Does NOT access private messages, user profiles, or non-public data
- ❌ Does NOT post, comment, vote, or modify any Reddit content
- ❌ Does NOT impersonate users or bots
- ❌ Does NOT use multiple accounts for the same use case

### ✅ Respecting Rate Limits

The application uses PRAW, which **automatically handles rate limiting** as per Reddit's API guidelines:

```python
# From bot.py - minimal API calls per search
for submission in subreddit_obj.new(limit=10):  # Only fetches 10 newest posts
```

- **Configurable check intervals**: Users can set refresh intervals from 1-60 minutes per monitor
- **Efficient querying**: Only fetches the 10 most recent posts per subreddit per check
- **No excessive polling**: Default interval is 10 minutes between checks
- **Deduplication**: Tracks processed submissions to avoid redundant processing

### ✅ Non-Commercial Use

This is a **purely non-commercial, personal utility tool**:

- **Open Source**: MIT License - freely available for anyone to use, modify, and distribute
- **No Monetization**: 
  - No ads, subscriptions, or paid features
  - No premium tiers or paywalls
  - No revenue generation of any kind
- **Self-Hosted Only**: Users run it on their own infrastructure (home server, NAS, VPS)
- **Personal Use**: Designed for individual users to monitor topics of personal interest

---

## Use Cases & Examples

### Legitimate Use Cases This Application Serves

| Use Case | Example |
|----------|---------|
| **Deal Hunting** | User monitors r/gamedeals for "free" game offers |
| **Hobby Tracking** | User monitors r/MechanicalKeyboards for specific keyboard models |
| **Local Community** | User monitors their local subreddit for neighborhood news |
| **Professional Alerts** | Developer monitors r/webdev for job postings in their tech stack |
| **Shopping Alerts** | User monitors r/buildapcsales for specific GPU models |
| **Research Tracking** | Researcher monitors academic subreddits for new papers |

### How Users Benefit

1. **Stay Informed**: Get instant alerts for topics that matter to them
2. **Save Time**: No need to constantly refresh Reddit manually
3. **Never Miss Posts**: Important posts won't get buried before users see them
4. **Customizable**: Each user configures exactly what they want to track

---

## Technical Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Self-Hosted Server                 │
├─────────────────┬─────────────────┬─────────────────────────┤
│   Bot Service   │   API Service   │   Frontend (Web UI)     │
│   (bot.py)      │   (api.py)      │   (Next.js)             │
│                 │                 │                          │
│ • Searches      │ • Config mgmt   │ • Monitor management    │
│   Reddit API    │ • REST API      │ • Settings interface    │
│ • Sends         │                 │                          │
│   notifications │                 │                          │
└────────┬────────┴─────────────────┴─────────────────────────┘
         │
         ▼ OAuth2 Authentication (Script Type)
┌─────────────────────────────────────────────────────────────┐
│              Reddit API (via PRAW)                          │
│              • Read public subreddit posts                  │
│              • Rate-limited by PRAW                         │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. User configures monitors via web UI (subreddit + keywords)
2. Bot periodically queries Reddit API for new posts
3. Bot filters posts against user criteria
4. If match found, notification sent to user's devices
5. Processed post IDs stored locally to prevent duplicates

### Data Storage (Local Only)

| File | Purpose | Contains Reddit Data? |
|------|---------|----------------------|
| `search.json` | Monitor configurations | No - only user settings |
| `credentials.json` | API credentials (encrypted) | No - only OAuth tokens |
| `processed_submissions.pkl` | Processed post IDs (deduplication) | Post IDs only (for deduplication) |

**Note**: Post content is NOT stored. Only submission IDs are cached temporarily to prevent sending duplicate notifications.

---

## API Usage Details

### Endpoints Used

| Endpoint | Purpose | Frequency |
|----------|---------|-----------|
| `/r/{subreddit}/new` | Get newest posts in a subreddit | Once per monitor per interval (1-60 min) |
| `/api/search_reddit_names` | Validate subreddit exists (UI only) | On-demand (user action) |

### Authentication Method

- **Type**: OAuth2 "script" application (personal use)
- **Scope**: Read-only access to public subreddit data
- **User Agent**: Clearly identifies the application per Reddit guidelines

```python
# From bot.py - proper authentication
return praw.Reddit(
    client_id=client_id,
    client_secret=client_secret,
    user_agent=user_agent,  # e.g., "RedditMonitor/1.0 by /u/username"
    username=username,
    password=password
)
```

### Rate Limit Compliance

PRAW automatically handles rate limiting, but the application also:
- Limits API calls to 10 posts per subreddit per check
- Uses configurable intervals (default 10 minutes) between checks
- Does not make excessive requests or attempt to circumvent limits

---

## Privacy & Security

### User Privacy

- **No data collection**: The application does not collect any user data
- **Self-hosted**: All data remains on the user's own server
- **No analytics**: No tracking, telemetry, or usage data sent anywhere
- **No third-party sharing**: Reddit data is never shared with any third party

### Reddit Community Privacy

- **Public data only**: Accesses only publicly available subreddit posts
- **No user profiling**: Does not track, analyze, or profile Reddit users
- **No content storage**: Post content is not stored, only displayed in notifications
- **Respectful queries**: Minimal, efficient API usage that doesn't burden Reddit's infrastructure

---

## Developer Information

### About Me

I'm an individual developer who created this tool for personal use and decided to open-source it to help others who want similar functionality. This is a hobby project with no commercial intentions.

### Contact Information

- **GitHub**: [@zarif98](https://github.com/zarif98)
- **Repository**: [Reddit-Scraper-with-Push-Notifications](https://github.com/zarif98/Reddit-Scraper-with-Push-Notifications)

### Project History

- **Started**: Personal project to get notifications for game deals
- **Open-Sourced**: Shared to help the community
- **Maintained**: Actively maintained and updated
- **Community**: MIT License allows others to use and contribute

---

## Compliance Summary

| Requirement | Status | Details |
|-------------|--------|---------|
| Transparency about data use | ✅ Compliant | Clear documentation of all functionality |
| Honest representation of intent | ✅ Compliant | Personal notification tool, no hidden purposes |
| Respects rate limits | ✅ Compliant | PRAW + configurable intervals + minimal queries |
| No commercial use | ✅ Compliant | Open source, no monetization |
| No AI/ML training | ✅ Compliant | Data not stored or used for training |
| No data selling/sharing | ✅ Compliant | Self-hosted, no third-party involvement |
| Proper authentication | ✅ Compliant | OAuth2 script app with clear user agent |
| Single account per use case | ✅ Compliant | One user = one account = one installation |

---

## Requested API Access

**Requested Tier**: Free (Non-Commercial)

**API Actions Required**:
- Read public subreddit posts (`/r/{subreddit}/new`)
- Validate subreddit names (`/api/search_reddit_names`)

**Estimated Usage**:
- ~60-100 API requests per hour per active user (varies by configuration)
- Well within Reddit's free tier limits

---

## Conclusion

Reddit Monitor is a simple, transparent, non-commercial tool that helps individual users stay informed about topics they care about. It:

1. **Respects Reddit's infrastructure** through rate limiting and efficient queries
2. **Protects user privacy** through self-hosting and no data collection
3. **Benefits the Reddit community** by keeping users engaged with content
4. **Follows all guidelines** in Reddit's Responsible Builder Policy

I am committed to maintaining compliance with Reddit's policies and will promptly address any concerns or required changes.

Thank you for considering this application.
