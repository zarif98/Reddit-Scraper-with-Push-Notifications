export interface Monitor {
    id: string;
    name: string;
    subreddit: string;
    keywords: string[];
    exclude_keywords: string[];
    min_upvotes: number | null;
    color: string;
    enabled: boolean;
    cooldown_minutes: number;
    max_post_age_hours: number;
}

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
    cooldown_minutes: 5,
    max_post_age_hours: 12,
};
