"""Shared package for the Reddit scraper bot and its web API.

Modules are layered so imports never cycle:
    config      -> (no internal deps)
    credentials -> config
    status      -> config, credentials
    notifications -> credentials
    sources     -> config, status, notifications
    health      -> config, credentials, sources
    monitor     -> config, credentials, notifications, sources

bot.py and api.py are thin entrypoints over these modules.
"""
