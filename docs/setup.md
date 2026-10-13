# Setup Guide

Complete setup guide for brief-mcp, including Google Calendar OAuth2 and
Brave Search API configuration.

---

## Prerequisites

- Python 3.11 or newer
- A Google account (for Calendar access)
- A Brave Search API key (free tier available — optional, DuckDuckGo fallback works without it)

---

## 1. Install brief-mcp

### With uv (recommended)

```bash
# One-shot run without installing
uvx brief-mcp

# Or install into a project
uv add brief-mcp
```

### With pip

```bash
pip install brief-mcp
```

---

## 2. Create a .env file

Create a `.env` file in your working directory (or wherever you run `brief-mcp` from):

```dotenv
# Required for Google Calendar integration
GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json

# Optional — use Brave Search instead of DuckDuckGo fallback
BRAVE_API_KEY=BSAxxx...

# Optional — enable Gmail prior-context enrichment
BRIEF_MCP_GMAIL_ENABLED=false

# Optional — logging verbosity (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=WARNING
```

---

## 3. Google Calendar OAuth2 Setup

### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Click **New Project** → name it "brief-mcp" → Create.
3. Select your new project from the dropdown.

### Step 2 — Enable the Calendar API

1. Go to **APIs & Services > Library**.
2. Search for "Google Calendar API".
3. Click **Enable**.

If you also want Gmail context enrichment:
1. Search for "Gmail API".
2. Click **Enable**.

### Step 3 — Create OAuth2 credentials

1. Go to **APIs & Services > Credentials**.
2. Click **+ Create Credentials > OAuth client ID**.
3. Choose **Desktop app**.
4. Name it "brief-mcp" → click **Create**.
5. Click **Download JSON** — save the file as `credentials.json`.
6. Set `GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json` in your `.env`.

### Step 4 — Configure the OAuth consent screen

1. Go to **APIs & Services > OAuth consent screen**.
2. Choose **External** (or Internal if using Google Workspace).
3. Fill in the required fields:
   - App name: "brief-mcp"
   - User support email: your email
4. Under **Scopes**, add:
   - `.../auth/calendar.readonly`
   - `.../auth/gmail.readonly` (if Gmail enabled)
5. Add your Gmail address under **Test users** (required for External apps).
6. Save.

### Step 5 — First run (OAuth browser flow)

The first time you run `brief-mcp`, it will open a browser window for you to
grant Calendar access. After you approve:

- A token is saved to `~/.brief-mcp/token.json`.
- All subsequent runs refresh the token automatically.
- The token file contains your OAuth refresh token — keep it private.

---

## 4. Brave Search API (optional)

Without a Brave API key, brief-mcp falls back to DuckDuckGo HTML scraping,
which works but is slower and less reliable.

For best results:

1. Sign up at [brave.com/search/api](https://brave.com/search/api/).
2. The **Free tier** gives 2,000 queries/month — enough for daily meeting prep.
3. Copy your API key and set `BRAVE_API_KEY=BSAxxx...` in your `.env`.

---

## 5. Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "brief-mcp": {
      "command": "uvx",
      "args": ["brief-mcp"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "/path/to/credentials.json",
        "BRAVE_API_KEY": "BSAxxx..."
      }
    }
  }
}
```

Restart Claude Desktop after saving.

---

## 6. VS Code / Cursor Configuration

Add to `.vscode/mcp.json` in your workspace (or user `settings.json`):

```json
{
  "servers": {
    "brief-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["brief-mcp"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "${workspaceFolder}/credentials.json",
        "BRAVE_API_KEY": "BSAxxx..."
      }
    }
  }
}
```

---

## 7. Zed Configuration

In `~/.config/zed/settings.json`:

```json
{
  "assistant": {
    "mcp_servers": {
      "brief-mcp": {
        "command": "uvx",
        "args": ["brief-mcp"],
        "env": {
          "GOOGLE_CREDENTIALS_PATH": "/path/to/credentials.json"
        }
      }
    }
  }
}
```

---

## 8. Privacy Notes

- brief-mcp runs **entirely on your machine**.
- The only outbound network calls are:
  - To Google Calendar / Gmail APIs (authenticated with your own OAuth token)
  - To Brave Search API or DuckDuckGo (anonymized search queries — name + company only)
- No meeting data, attendee names, or calendar content is ever sent to Anthropic or any third party.
- The OAuth token in `~/.brief-mcp/token.json` is read-only Calendar + Gmail access.

---

## Troubleshooting

**"GOOGLE_CREDENTIALS_PATH not set"** — Set the env var in your `.env` file or MCP config.

**"credentials.json not found"** — Download it from Google Cloud Console (step 3 above).

**OAuth browser window doesn't open** — Run `brief-mcp` directly from a terminal for the first auth.

**"Token expired" errors** — Delete `~/.brief-mcp/token.json` and re-run to re-authenticate.

**No meetings returned** — Check your Google Calendar has events in the next 24 hours and that the API is enabled for your project.

**DuckDuckGo returning empty results** — DuckDuckGo rate-limits scrapers. Add a `BRAVE_API_KEY` for reliable results.
