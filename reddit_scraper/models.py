"""Pydantic models — the single schema-of-record for data shared across the stack.

The frontend's TypeScript types are generated from these models (see scripts/gen_types.py),
so a field renamed/added/removed here flows to the UI instead of drifting. The backend also
validates/serializes monitors through `Monitor` (create/update/normalize all go through it),
so field defaults and the tidy on-disk shape live here and nowhere else. See CLAUDE.md
("Single source of truth").
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Optional list fields dropped from the stored form when empty (keeps search.json tidy).
OPTIONAL_LIST_FIELDS = (
    'exclude_keywords',
    'domain_contains',
    'domain_excludes',
    'flair_contains',
    'author_includes',
    'author_excludes',
)


class Monitor(BaseModel):
    """A monitor as persisted in search.json ('subreddits_to_search' entries).

    Defaults live here. `extra='allow'` preserves any bot-only or legacy fields (e.g.
    monitor_type / thread_title_pattern / keyword_logic on hand-configured thread monitors)
    so routing an existing monitor through the model never drops data.
    """

    model_config = ConfigDict(extra='allow')

    id: str
    name: str = ''
    subreddit: str
    color: str
    enabled: bool = True
    cooldown_minutes: int = 10
    max_post_age_hours: int = 12
    min_upvotes: Optional[int] = None
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    domain_contains: list[str] = Field(default_factory=list)
    domain_excludes: list[str] = Field(default_factory=list)
    flair_contains: list[str] = Field(default_factory=list)
    author_includes: list[str] = Field(default_factory=list)
    author_excludes: list[str] = Field(default_factory=list)

    @field_validator('subreddit')
    @classmethod
    def _normalize_subreddit(cls, v: str) -> str:
        return v.strip().lower().replace('r/', '')

    @model_validator(mode='after')
    def _default_name(self):
        if not self.name:
            self.name = f'r/{self.subreddit}'
        return self

    def to_stored_dict(self) -> dict:
        """Dict for search.json: drops empty optional lists and a null min_upvotes to keep the
        file tidy (matches the old config.clean_monitor). Bot-only/legacy fields pass through."""
        data = self.model_dump()
        for field in OPTIONAL_LIST_FIELDS:
            if not data.get(field):
                data.pop(field, None)
        if data.get('min_upvotes') is None:
            data.pop('min_upvotes', None)
        return data
