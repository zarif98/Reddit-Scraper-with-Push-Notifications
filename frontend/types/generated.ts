// AUTO-GENERATED from reddit_scraper/models.py — do not edit by hand.
// Regenerate with: npm run gen:types (from frontend/) or python3 scripts/gen_types.py

/**
 * A monitor as persisted in search.json ('subreddits_to_search' entries).
 *
 * Defaults live here. `extra='allow'` preserves any bot-only or legacy fields (e.g.
 * monitor_type / thread_title_pattern / keyword_logic on hand-configured thread monitors)
 * so routing an existing monitor through the model never drops data.
 */
export interface Monitor {
  id: string;
  name?: string;
  subreddit: string;
  color: string;
  enabled?: boolean;
  cooldown_minutes?: number;
  max_post_age_hours?: number;
  min_upvotes?: number | null;
  keywords?: string[];
  exclude_keywords?: string[];
  domain_contains?: string[];
  domain_excludes?: string[];
  flair_contains?: string[];
  author_includes?: string[];
  author_excludes?: string[];
  [k: string]: unknown;
}
