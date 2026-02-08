# Reddit Monitor with Push Notifications

A self-hosted Reddit monitoring bot with a modern web UI. Get instant notifications via **Discord, Slack, Telegram, Pushover, and 80+ other services** when posts matching your keywords appear in your favorite subreddits.

## 📸 Screenshots

| Monitor List | Mobile View | Edit Monitor | Notifications |
|:---:|:---:|:---:|:---:|
| ![Monitor List](SCR-20260109-jcdr.png) | ![Mobile View](SCR-20260110-inmx.png) | ![Edit Modal](SCR-20260110-inpp.png) | ![Notifications](image.png) |

## ✨ Features

- **🌐 Web UI** - Beautiful dark-themed interface to manage monitors from any device
- **📱 Mobile Friendly** - Works great on phones and tablets
- **🔔 80+ Notification Services** - Discord, Slack, Telegram, Pushover, ntfy, Email, and more via [Apprise](https://github.com/caronc/apprise)
- **⏱️ Per-Monitor Refresh** - Each monitor can have its own check interval (1 min to 1 hour)
- **🎯 Advanced Filters** - Keywords, exclusions, domain filters, flair filters, author filters
- **🐳 Docker Ready** - Easy deployment with Docker Compose
- **🔄 Auto Updates** - Works with Watchtower for automatic container updates
- **⚙️ Web-Based Setup** - Configure Reddit & notification services via the UI

## 🚀 Quick Start (Docker)

### 1. Create docker-compose.yml

```yaml
version: '3.8'

services:
  bot:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:latest
    container_name: reddit-bot
    command: ["python", "bot.py"]
    restart: unless-stopped
    environment:
      - DATA_DIR=/data
      - TZ=America/Los_Angeles  # Set your timezone
    volumes:
      - ./data:/data
    depends_on:
      - api

  api:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:latest
    container_name: reddit-api
    command: ["python", "api.py"]
    restart: unless-stopped
    ports:
      - "5040:5001"
    environment:
      - DATA_DIR=/data
      - TZ=America/Los_Angeles
    volumes:
      - ./data:/data

  frontend:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:frontend
    container_name: reddit-frontend
    restart: unless-stopped
    ports:
      - "8080:3000"
    environment:
      - TZ=America/Los_Angeles
    depends_on:
      - api
```

### 2. Start the Stack

```bash
docker-compose up -d
```

### 3. Configure Credentials

1. Open `http://localhost:8080` (or `http://YOUR_IP:8080`)
2. Click **Configure Settings**
3. Enter your Reddit API credentials and notification service URLs
4. Save - the bot will automatically start monitoring!

## 📦 Data Persistence

All data is stored in the `/data` volume:

```
./data/
├── search.json          # Your monitors configuration
├── credentials.json     # Reddit & notification credentials
└── processed_submissions.pkl  # Tracks sent notifications
```

## ⚙️ Configuration

### Getting Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Note your `client_id` (under the app name) and `client_secret`

### Setting Up Notifications

This app uses [Apprise](https://github.com/caronc/apprise) to support 80+ notification services. Configure notifications in the Settings modal using Apprise URLs.

**Popular services:**
| Service | URL Format |
|---------|------------|
| Discord | `discord://webhook_id/webhook_token` |
| Slack | `slack://token_a/token_b/token_c/#channel` |
| Telegram | `tgram://bot_token/chat_id` |
| Pushover | `pover://user_key@api_token` |
| ntfy | `ntfy://topic` |
| Email | `mailto://user:pass@gmail.com` |

See the [Apprise Wiki](https://github.com/caronc/apprise/wiki) for all supported services and URL formats.

### Monitor Options

Each monitor supports these options:

| Field | Description | Default |
|-------|-------------|---------|
| `name` | Display name for the monitor | Auto-generated |
| `subreddit` | Subreddit to monitor (without r/) | Required |
| `keywords` | Words to match in post titles | Required |
| `exclude_keywords` | Words to exclude | `[]` |
| `min_upvotes` | Minimum upvotes required | `null` |
| `cooldown_minutes` | Refresh interval (1-60 min) | `10` |
| `max_post_age_hours` | Ignore posts older than this | `12` |
| `domain_contains` | Only match these domains | `[]` |
| `domain_excludes` | Exclude these domains | `[]` |
| `flair_contains` | Only match these flairs | `[]` |
| `author_includes` | Only from these authors | `[]` |
| `author_excludes` | Ignore these authors | `[]` |
| `enabled` | Active/inactive toggle | `true` |
| `color` | UI card color | Auto-assigned |

### Example search.json

```json
{
    "subreddits_to_search": [
        {
            "id": "example-1",
            "name": "Free Games",
            "subreddit": "gamedeals",
            "keywords": ["free", "100%"],
            "exclude_keywords": ["demo"],
            "cooldown_minutes": 2,
            "domain_contains": ["epicgames.com", "steam"],
            "enabled": true
        }
    ]
}
```

## 🖥️ Local Development

### Backend (API + Bot)

```bash
# Install dependencies
pip install -r requirements.txt

# Run API server
python api.py

# Run bot (in another terminal)
python bot.py
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Access at http://localhost:3000

## 🛠️ Synology NAS Deployment

1. **Create data directory**: `/volume1/docker/reddit-monitor/data`

2. **Deploy via Portainer** as a Stack with the docker-compose above

3. **Port Configuration**:
   - Frontend: `8080:3000`
   - API: `5040:5001` (avoid 5001, used by Synology DSM)

4. **Add Watchtower** for auto-updates:
   ```yaml
   watchtower:
     image: containrrr/watchtower
     volumes:
       - /var/run/docker.sock:/var/run/docker.sock
     command: --interval 3600
   ```

## 🔒 Private Network Configuration (Advanced)

By default, the frontend auto-detects the API URL based on your browser's hostname. For Docker private networks where containers communicate by name, you can override this using environment variables.

### Example: Fully Private docker-compose.yml

```yaml
services:
  bot:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:latest
    # ... same as before

  api:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:latest
    command: ["python", "api.py"]
    # No ports exposed to host - only accessible within Docker network
    expose:
      - "5001"
    volumes:
      - ./data:/data

  frontend:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:frontend
    ports:
      - "8080:3000"  # Only frontend exposed to host
    environment:
      - NEXT_PUBLIC_API_URL=http://api:5001
    depends_on:
      - api
```

This allows the frontend container to reach the API via the internal Docker network (`http://api:5001`) without exposing the API port on the host.

## 🔄 API Fallback Mode

If Reddit's API becomes unavailable or your credentials expire, the bot will automatically switch to **JSON fallback mode**. This mode fetches posts directly from Reddit's public JSON endpoints without requiring API authentication.

### How it works

1. Bot attempts to use the Reddit API (PRAW) for each request
2. If authentication fails (401 error), bot automatically switches to JSON fallback
3. A warning banner appears at the top of the web UI indicating fallback mode is active
4. Bot continues monitoring normally using `old.reddit.com/r/subreddit/new.json`
5. When API access is restored, the warning disappears automatically

### Limitations of fallback mode

- May be subject to stricter rate limiting
- Some advanced Reddit features may not be available
- Less reliable than authenticated API access

### To restore API access

1. Check your Reddit API credentials in Settings
2. Verify your app hasn't been rate-limited or banned
3. Create new API credentials at https://www.reddit.com/prefs/apps if needed

## 🔧 Troubleshooting

### Bot shows "Waiting for credentials"
Configure credentials at `http://YOUR_IP:8080` → Settings

### CORS errors
Ensure API container is running and port mapping is correct

## 📄 License

MIT License - see LICENSE file for details.
