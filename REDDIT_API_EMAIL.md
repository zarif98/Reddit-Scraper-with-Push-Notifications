# Reddit Data API Application - Email Template

---

**Subject:** Re: Reddit Data API Access Request #16666795 - Additional Details

---

Hi Reddit Data API Team,

Thank you for your response regarding my application. I'd like to provide additional details to address the Responsible Builder Policy requirements.

## Application Summary

**Project:** Reddit Monitor - Personal Notification Tool  
**Type:** Non-commercial, open-source, self-hosted  
**Repository:** https://github.com/zarif98/Reddit-Scraper-with-Push-Notifications  
**License:** MIT (completely free)

## What It Does

A simple personal tool that sends push notifications when new posts match keywords I'm interested in. For example, I use it to get alerts when free games are posted in r/gamedeals.

**Technical details:**
- Uses PRAW (Reddit's official Python library)
- OAuth2 "script" authentication (personal use)
- Read-only access to public subreddit posts
- Fetches only 10 newest posts per check
- Configurable intervals (default: every 10 minutes)

## Policy Compliance

| Requirement | How I Comply |
|-------------|--------------|
| **Transparency** | Open-source code, clear documentation |
| **Rate limits** | PRAW handles limits; minimal efficient queries |
| **Non-commercial** | No ads, no subscriptions, no revenue |
| **No AI training** | Data not stored or used for ML |
| **No data sharing** | Self-hosted only, nothing sent to third parties |

## What I'm NOT Doing

- ❌ No bulk scraping or data archiving
- ❌ No user profiling or tracking
- ❌ No commercial use or monetization
- ❌ No AI/ML model training
- ❌ No data selling or sharing

## API Access Needed

- **Endpoint:** `/r/{subreddit}/new` (read public posts)
- **Tier:** Free (non-commercial)
- **Usage:** ~60-100 requests/hour (well within limits)

I'm happy to provide any additional information or make changes if needed.

Thank you,  
[Your Name]

---

*Full technical documentation available at: REDDIT_API_APPLICATION.md in the repository*
