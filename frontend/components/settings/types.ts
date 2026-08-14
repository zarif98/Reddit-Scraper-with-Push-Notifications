export interface Credentials {
    reddit_client_id: string;
    reddit_client_secret: string;
    reddit_username: string;
    reddit_password: string;
    reddit_user_agent: string;
    sylvia_api_key: string;
    notification_urls: string[];
}

export const DEFAULT_CREDENTIALS: Credentials = {
    reddit_client_id: '',
    reddit_client_secret: '',
    reddit_username: '',
    reddit_password: '',
    reddit_user_agent: '',
    sylvia_api_key: '',
    notification_urls: [],
};

export type DataSource = 'reddit' | 'sylvia';
