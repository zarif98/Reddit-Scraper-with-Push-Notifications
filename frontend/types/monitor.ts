// Monitor is generated from reddit_scraper/models.py (the schema-of-record).
// Regenerate with `npm run gen:types`. Don't hand-write this shape here.
export type { Monitor } from './generated';
import type { Monitor } from './generated';

// MUST stay in sync with DEFAULT_COLORS in reddit_scraper/config.py (backend auto-assigns
// from that list on create; this is the picker) — keep the two lists identical.
export const DEFAULT_COLORS = [
    '#8B5CF6', // Purple
    '#3B82F6', // Blue
    '#22C55E', // Green
    '#EF4444', // Red
    '#F97316', // Orange
    '#EC4899', // Pink
    '#06B6D4', // Cyan
    '#EAB308', // Yellow
    '#10B981', // Emerald
    '#F43F5E', // Rose
];

export const DEFAULT_MONITOR: Partial<Monitor> = {
    name: '',
    subreddit: '',
    keywords: [],
    exclude_keywords: [],
    min_upvotes: null,
    color: DEFAULT_COLORS[0],
    enabled: true,
    cooldown_minutes: 10,
    max_post_age_hours: 12,
    domain_contains: [],
    domain_excludes: [],
    flair_contains: [],
    author_includes: [],
    author_excludes: [],
};
