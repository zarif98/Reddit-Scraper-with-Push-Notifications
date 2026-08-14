"""Pydantic models — the single schema-of-record for data shared across the stack.

The frontend's TypeScript types are generated from these models (see scripts/gen_types.py),
so a field renamed/added/removed here flows to the UI instead of drifting. See CLAUDE.md
("Single source of truth"). Backend validation/serialization against these models is being
adopted incrementally.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Monitor(BaseModel):
    """A monitor as persisted in search.json ('subreddits_to_search' entries).

    Fields with defaults are optional on create (the API/config supplies them); id, name,
    subreddit, and color are always present on a stored monitor.
    """

    id: str
    name: str
    subreddit: str
    color: str
    enabled: bool = True
    cooldown_minutes: int = 10
    max_post_age_hours: int = 12
    min_upvotes: Optional[int] = None
    keyword_logic: str = 'any'
    monitor_type: str = 'posts'
    thread_title_pattern: str = 'Buy/Sell/Trade'
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    domain_contains: list[str] = Field(default_factory=list)
    domain_excludes: list[str] = Field(default_factory=list)
    flair_contains: list[str] = Field(default_factory=list)
    author_includes: list[str] = Field(default_factory=list)
    author_excludes: list[str] = Field(default_factory=list)
