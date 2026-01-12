# Reddit Monitor with Push Notifications

A self-hosted Reddit monitoring bot with a modern web UI. Get instant notifications via **Discord, Slack, Telegram, Pushover, and 80+ other services** when posts matching your keywords appear in your favorite subreddits.

## 📸 Screenshots

| Monitor List | Mobile View | Edit Monitor |
|:---:|:---:|:---:|
| ![Monitor List](SCR-20260109-jcdr.png) | ![Mobile View](SCR-20260110-inmx.png) | ![Edit Modal](SCR-20260110-inpp.png) |

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
    volumes:
      - ./data:/data

  frontend:
    image: ghcr.io/zarif98/reddit-scraper-with-push-notifications:frontend
    container_name: reddit-frontend
    restart: unless-stopped
    ports:
      - "8080:3000"
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
3. Enter your Reddit API credentials and Pushover keys
4. Save - the bot will automatically start monitoring!

## 📦 Data Persistence

All data is stored in the `/data` volume:

```
./data/
├── search.json          # Your monitors configuration
├── credentials.json     # Reddit & Pushover credentials
└── processed_submissions.pkl  # Tracks sent notifications
```

## ⚙️ Configuration

### Getting Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Note your `client_id` (under the app name) and `client_secret`

### Getting Pushover Credentials

1. Sign up at https://pushover.net
2. Note your **User Key** from the dashboard
3. Create an application to get an **API Token**

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

## 🔧 Troubleshooting

### Bot shows "Waiting for credentials"
Configure credentials at `http://YOUR_IP:8080` → Settings

### CORS errors
Ensure API container is running and port mapping is correct

## 📄 License

MIT License - see LICENSE file for details.
