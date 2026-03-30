# Deploying Market Watcher on UGreen DXP4800+

Step-by-step guide to running Market Watcher as a Docker container on your UGreen DXP4800+ NAS.

## Prerequisites

- UGreen DXP4800+ with UGOS Pro installed
- Docker enabled on your NAS (Settings > Docker in the UGOS web UI)
- SSH access to the NAS (Settings > Terminal & SNMP > Enable SSH)
- Telegram bot already configured (see [telegram_setup.md](telegram_setup.md))

## Option A: SSH + Docker Compose (Recommended)

This is the most reliable method and gives you full control.

### 1. SSH into your NAS

```bash
ssh root@<your-nas-ip>
```

Replace `<your-nas-ip>` with your NAS's local IP address (find it in the UGOS dashboard or your router's client list).

### 2. Create a project directory

Pick a location on one of your storage volumes. The DXP4800+ mounts volumes under `/volume1`, `/volume2`, etc.

```bash
mkdir -p /volume1/docker/market-watcher
cd /volume1/docker/market-watcher
```

### 3. Transfer the project files

From your local machine (not the NAS), copy the project over:

```bash
# From your Mac, in the market-watcher directory:
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'data/' --exclude 'logs/' \
  ./ root@<your-nas-ip>:/volume1/docker/market-watcher/
```

Or use SCP:

```bash
scp -r ./ root@<your-nas-ip>:/volume1/docker/market-watcher/
```

### 4. Create the .env file

On the NAS:

```bash
cd /volume1/docker/market-watcher
cp .env.example .env
```

Edit it with your Telegram credentials:

```bash
vi .env
```

```
TELEGRAM_BOT_TOKEN=your_actual_bot_token
TELEGRAM_CHAT_ID=your_actual_chat_id
LOG_LEVEL=INFO
```

### 5. Create persistent data directories

```bash
mkdir -p data logs
```

### 6. Build and start the container

```bash
docker compose up -d --build
```

> If your UGOS version uses the older Docker Compose plugin, use `docker-compose up -d --build` instead.

### 7. Verify it's running

```bash
docker compose logs -f
```

You should see:

```
market-watcher  | Market Watcher starting...
market-watcher  | Scheduled scans:
market-watcher  |   - Hourly: 9:30 AM - 3:30 PM ET, Monday-Friday
market-watcher  |   - Market open: 9:35 AM ET, Monday-Friday
```

Press `Ctrl+C` to stop following the logs (the container keeps running).

## Option B: UGOS Docker UI

If you prefer the graphical interface, you'll need to build the image via SSH first, then manage it in the UI.

### 1. Build the image via SSH

```bash
ssh root@<your-nas-ip>
cd /volume1/docker/market-watcher
docker build -t market-watcher .
```

### 2. Create the container in UGOS

1. Open the UGOS web UI and go to **Docker**
2. Go to **Images** -- you should see `market-watcher`
3. Click **Run** / **Create Container** on the image
4. Configure the container:

| Setting | Value |
|---|---|
| Container Name | `market-watcher` |
| Restart Policy | `Unless Stopped` |
| Memory Limit | `512 MB` |
| CPU Limit | `1 core` |

5. **Environment Variables** -- add:
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat ID
   - `TZ` = `America/New_York`
   - `LOG_LEVEL` = `INFO`

6. **Volumes** -- bind mount these paths:

| Container Path | Host Path | Purpose |
|---|---|---|
| `/app/data` | `/volume1/docker/market-watcher/data` | Stock data cache |
| `/app/logs` | `/volume1/docker/market-watcher/logs` | Application logs |
| `/app/alert_state.json` | `/volume1/docker/market-watcher/alert_state.json` | Alert cooldown state |
| `/app/alert_outcomes.json` | `/volume1/docker/market-watcher/alert_outcomes.json` | Learning outcomes |
| `/app/weight_history.json` | `/volume1/docker/market-watcher/weight_history.json` | Weight adjustments |

> For the JSON file mounts, create empty files first so Docker doesn't create them as directories:
> ```bash
> touch /volume1/docker/market-watcher/alert_state.json
> touch /volume1/docker/market-watcher/alert_outcomes.json
> touch /volume1/docker/market-watcher/weight_history.json
> ```

7. Click **Create** / **Run**

## Testing

### Test Telegram connectivity

```bash
docker compose exec market-watcher python run_scanner.py --test
```

### Run a single scan manually

```bash
docker compose exec market-watcher python run_scanner.py --once
```

### Scan a specific ticker

```bash
docker compose exec market-watcher python run_scanner.py --ticker AAPL
```

### Run the learning cycle manually

```bash
docker compose exec market-watcher python run_scanner.py --learn
```

## Resource Usage

The `docker-compose.yml` is already configured with NAS-friendly limits:

- **Memory**: 512 MB cap
- **CPU**: 1 core cap
- **Logs**: Capped at 10 MB with 3 rotated files
- **Network**: Outbound only (yfinance API + Telegram API), no ports exposed

The DXP4800+ has an Intel N100 (4 cores, 6W TDP) and at least 8 GB RAM, so this container will have minimal impact on NAS performance.

## Managing the Container

### View logs

```bash
# Live logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail 100
```

### Stop / Start / Restart

```bash
docker compose stop
docker compose start
docker compose restart
```

### Update after code changes

After modifying the code or pulling updates:

```bash
# Re-sync files from your Mac
rsync -avz --exclude '__pycache__' --exclude '.git' --exclude 'data/' --exclude 'logs/' --exclude '.env' \
  ./ root@<your-nas-ip>:/volume1/docker/market-watcher/

# On the NAS, rebuild and restart
cd /volume1/docker/market-watcher
docker compose up -d --build
```

### Full cleanup

```bash
docker compose down --rmi local
```

This stops the container and removes the built image. Persistent data in `data/`, `logs/`, and the JSON state files is preserved.

## Troubleshooting

### Container exits immediately

Check the logs:

```bash
docker compose logs
```

Common causes:
- Missing or invalid `.env` file (the container will still start but Telegram alerts won't work)
- Python dependency issue -- rebuild with `docker compose build --no-cache`

### No alerts during market hours

1. Confirm the container is running: `docker compose ps`
2. Check that the timezone is correct: `docker compose exec market-watcher date` should show Eastern Time
3. Verify Telegram creds: `docker compose exec market-watcher python run_scanner.py --test`
4. Check if there are signals: `docker compose exec market-watcher python run_scanner.py --once --debug`

### DNS resolution failures

If yfinance or Telegram API calls fail with DNS errors, the NAS Docker network may need a DNS override. Add to `docker-compose.yml`:

```yaml
services:
  market-watcher:
    dns:
      - 8.8.8.8
      - 1.1.1.1
```

Then rebuild: `docker compose up -d`

### State files mounted as directories

If Docker created `alert_state.json` as a directory instead of a file:

```bash
docker compose down
rm -rf alert_state.json alert_outcomes.json weight_history.json
touch alert_state.json alert_outcomes.json weight_history.json
docker compose up -d
```

### Surviving NAS reboots

The `restart: unless-stopped` policy in `docker-compose.yml` ensures the container comes back up after a NAS reboot, as long as Docker itself starts on boot (enabled by default in UGOS).
