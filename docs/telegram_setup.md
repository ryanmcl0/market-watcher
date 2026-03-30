# Telegram Bot Setup Guide

This guide walks you through creating a Telegram bot for receiving Market Watcher alerts.

## Step 1: Create a Bot with BotFather

1. Open Telegram and search for `@BotFather`
2. Start a chat and send the command: `/newbot`
3. Follow the prompts:
   - **Name**: Choose a display name (e.g., "Market Watcher Alerts")
   - **Username**: Choose a unique username ending in `bot` (e.g., `my_market_alerts_bot`)

4. BotFather will respond with your **Bot Token**:
   ```
   Done! Congratulations on your new bot. You will find it at t.me/my_market_alerts_bot.

   Use this token to access the HTTP API:
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

5. **Save this token** - you'll need it for configuration.

## Step 2: Get Your Chat ID

You need to find your personal Chat ID so the bot knows where to send messages.

### Option A: Using @userinfobot (Easiest)

1. Search for `@userinfobot` in Telegram
2. Start a chat and send any message
3. The bot will reply with your user info including your **Chat ID**:
   ```
   Id: 123456789
   First: Your Name
   Lang: en
   ```

### Option B: Using the API

1. Start a chat with your new bot (search for it by username)
2. Send any message to your bot (e.g., "hello")
3. Open this URL in your browser (replace YOUR_TOKEN with your actual token):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
4. Look for `"chat":{"id":123456789}` in the response - that number is your Chat ID

### Option C: Group Chat (Optional)

If you want alerts sent to a group:

1. Create a new group or use an existing one
2. Add your bot to the group
3. Send a message in the group
4. Use the getUpdates API method above
5. The group Chat ID will be a negative number (e.g., `-987654321`)

## Step 3: Configure Market Watcher

### Method 1: Environment Variables (Recommended for Docker)

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

### Method 2: Direct Configuration

Edit `config.py` and set the values directly (not recommended for security):

```python
TELEGRAM_CONFIG = {
    'bot_token': '123456789:ABCdefGHIjklMNOpqrsTUVwxyz',
    'chat_id': '123456789',
    ...
}
```

## Step 4: Test the Connection

Run the test command:

```bash
python run_scanner.py --test
```

You should see:

```
Testing Telegram connection...
Bot connection: OK
Message send: OK

Telegram connection successful!
```

And receive a test message in Telegram.

## Troubleshooting

### "Bot connection: FAILED"

- Double-check your bot token is correct
- Make sure there are no extra spaces or characters
- Verify the token hasn't been revoked in BotFather

### "Message send: FAILED"

- Verify your Chat ID is correct
- For group chats, make sure the bot is a member of the group
- For private chats, make sure you've sent at least one message to the bot first

### Not Receiving Messages

- Check that notifications are enabled for the chat
- Verify the bot isn't muted
- Make sure the Chat ID matches where you're looking

## Security Best Practices

1. **Never commit your `.env` file** to version control
2. **Keep your bot token secret** - anyone with the token can send messages as your bot
3. **Use environment variables** instead of hardcoding credentials
4. **Regularly check** BotFather for any unauthorized access

## Bot Commands (Optional)

You can configure custom commands for your bot in BotFather:

1. Open BotFather
2. Send `/setcommands`
3. Select your bot
4. Send:
   ```
   status - Check scanner status
   scan - Run immediate scan
   help - Show help information
   ```

(Note: These commands are informational only - the Market Watcher doesn't currently respond to Telegram commands)

## Rate Limits

Telegram has rate limits for bots:

- **Individual chats**: 1 message per second
- **Groups**: 20 messages per minute
- **Broadcast**: 30 messages per second across all chats

Market Watcher respects these limits by batching alerts into single messages.
