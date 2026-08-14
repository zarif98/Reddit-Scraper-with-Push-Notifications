"""Tests for the Pydantic schema-of-record and the generated-TS staleness guard."""

from pathlib import Path

from reddit_scraper import models

GENERATED_TS = Path(__file__).resolve().parent.parent / 'frontend' / 'types' / 'generated.ts'


class TestMonitorModel:
    def test_defaults_applied(self):
        m = models.Monitor(id='1', name='RDR', subreddit='gamedeals', color='#8B5CF6')
        assert m.enabled is True
        assert m.cooldown_minutes == 10
        assert m.max_post_age_hours == 12
        assert m.min_upvotes is None
        assert m.keywords == [] and m.domain_contains == []

    def test_normalizes_subreddit_and_defaults_name(self):
        m = models.Monitor(id='1', subreddit='R/GameDeals', color='#fff')
        assert m.subreddit == 'gamedeals'  # stripped/lowercased, r/ removed
        assert m.name == 'r/gamedeals'  # name defaults from subreddit

    def test_preserves_bot_only_fields(self):
        m = models.Monitor(id='1', subreddit='x', color='#fff', monitor_type='thread_comments')
        assert m.to_stored_dict()['monitor_type'] == 'thread_comments'  # extra='allow' passthrough

    def test_to_stored_dict_strips_empties(self):
        stored = models.Monitor(id='1', subreddit='x', color='#fff').to_stored_dict()
        assert 'exclude_keywords' not in stored and 'min_upvotes' not in stored
        assert stored['keywords'] == []  # keywords is always kept

    def test_round_trips_a_full_monitor(self):
        data = {
            'id': 'abc',
            'name': 'n',
            'subreddit': 's',
            'color': '#fff',
            'enabled': False,
            'cooldown_minutes': 5,
            'max_post_age_hours': 24,
            'min_upvotes': 100,
            'keywords': ['gpu'],
            'exclude_keywords': ['sold'],
            'domain_contains': ['store.example.com'],
            'domain_excludes': [],
            'flair_contains': [],
            'author_includes': [],
            'author_excludes': [],
        }
        assert models.Monitor(**data).model_dump()['min_upvotes'] == 100


class TestGeneratedTypesInSync:
    """Cheap guard (no node needed): every model field must appear in the committed
    generated.ts, so a field added without running `npm run gen:types` fails CI."""

    def test_generated_ts_has_every_model_field(self):
        ts = GENERATED_TS.read_text()
        missing = [f for f in models.Monitor.model_fields if f not in ts]
        assert not missing, f"generated.ts is stale (missing {missing}); run `npm run gen:types`"
