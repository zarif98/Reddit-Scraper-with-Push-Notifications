// AUTO-GENERATED from reddit_scraper/models.py — do not edit by hand.
// Regenerate with: npm run gen:types (from frontend/) or python3 scripts/gen_types.py

/**
 * A monitor as persisted in search.json ('subreddits_to_search' entries).
 *
 * Fields with defaults are optional on create (the API/config supplies them); id, name,
 * subreddit, and color are always present on a stored monitor.
 */
export interface Monitor {
  id: string;
  name: string;
  subreddit: string;
  color: string;
  enabled?: boolean;
  cooldown_minutes?: number;
  max_post_age_hours?: number;
  min_upvotes?: number | null;
  keyword_logic?: string;
  monitor_type?: string;
  thread_title_pattern?: string;
  keywords?: string[];
  exclude_keywords?: string[];
  domain_contains?: string[];
  domain_excludes?: string[];
  flair_contains?: string[];
  author_includes?: string[];
  author_excludes?: string[];
}
