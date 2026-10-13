# brief-mcp

> **Know everyone in the room before you walk in.**

[![PyPI version](https://img.shields.io/pypi/v/brief-mcp?color=blue&label=PyPI)](https://pypi.org/project/brief-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![MIT License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-purple)](https://modelcontextprotocol.io/)

A **Model Context Protocol (MCP) server** that gives Claude — and any MCP-compatible AI assistant — the ability to research meeting attendees and generate executive briefing cards before any meeting. Connects to your Google Calendar, runs parallel web research on every attendee, and returns a formatted brief in seconds.

---

## What it looks like

You open Claude and type: *"Brief me for my 2pm call."*

Claude responds:

```text
============================================================
  MEETING BRIEF: Q4 PARTNERSHIP REVIEW
============================================================

  When    : Tuesday, October 13 2026 at 02:00 PM
  Duration: 60 minutes
  Link    : https://meet.google.com/abc-defg-hij

  Attendees (3): Alice Chen (you), Bob Patel, Carol Wu

------------------------------------------------------------
  ATTENDEE PROFILES
------------------------------------------------------------

  >> Bob Patel
     Role    : VP of Engineering @ PartnerCo
     Bio     : Engineering leader, 15 years in distributed systems.
               Previously Staff Engineer at Google and DataStream Inc.
     Recent  :
       - Bob Patel promoted to VP of Engineering (Sept 2026)
       - PartnerCo Engineering Blog: new latency benchmarks published
     Co News :
       - PartnerCo raises $50M Series B to accelerate AI platform
       - PartnerCo announces APAC expansion, opens Singapore office

  >> Carol Wu
     Role    : Director of Product @ PartnerCo
     Bio     : Product leader, ex-Google PM for Firebase.
     Recent  :
       - Carol Wu joins PartnerCo from Google as Director of Product
       - Carol Wu keynote at ProductCon SF 2026

------------------------------------------------------------
  SUGGESTED TALKING POINTS
------------------------------------------------------------
  1. Ask Bob about engineering priorities and how the integration fits
     their new Kubernetes-native platform.
  2. Reference the Series B — congratulate them and probe roadmap changes.
  3. Carol is new from Google — don't assume prior integration context.
  4. Confirm next-steps owner before the call ends.

------------------------------------------------------------
  WATCH-OUTS
------------------------------------------------------------
  ! Series B funding may prompt renegotiation — know your commercial floor.
  ! Carol joined in 2026 — bring her up to speed on integration history.

  Generated: 2026-10-13 09:14
============================================================
```

All of that from a single message to Claude. No browser tabs, no LinkedIn spelunking.

---

## Install

### One-command (no install needed)

```bash
uvx brief-mcp
```

### pip

```bash
pip install brief-mcp
```

### From source

```bash
git clone https://github.com/MLDreamer/brief-mcp
cd brief-mcp
uv sync
uv run brief-mcp
```

---

## Quick Start

**1. Get a Google credentials.json** (one-time, 5 minutes — [full guide](docs/setup.md)):

```text
Google Cloud Console → APIs → Google Calendar API → Enable
                     → Credentials → OAuth 2.0 Desktop App → Download JSON
```

**2. Create `.env`:**

```dotenv
GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
BRAVE_API_KEY=BSAxxx...          # optional — free at brave.com/search/api
```

**3. Add to Claude Desktop** — see config below.

**4. Open Claude and say:** `"Brief me for today's meetings."`

---

## Claude Desktop Configuration

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "brief-mcp": {
      "command": "uvx",
      "args": ["brief-mcp"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "/Users/you/credentials.json",
        "BRAVE_API_KEY": "BSAxxx..."
      }
    }
  }
}
```

Restart Claude Desktop.

---

## VS Code / Cursor Configuration

Add to `.vscode/mcp.json` in your workspace:

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

## Zed Configuration

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

## Available Tools

| Tool | What it does |
| --- | --- |
| `get_upcoming_meetings` | Reads Google Calendar → returns meetings in the next N hours with attendees and video links |
| `research_attendee` | Web search + news on a person and their company → structured profile (cached 60 min) |
| `get_meeting_brief` | Looks up one meeting, researches all attendees in parallel → formatted brief card |
| `brief_all_today` | Generates briefs for every meeting today, deduplicating attendee research across meetings |
| `get_outlook_meetings` | Reads Outlook/Microsoft 365 Calendar via Microsoft Graph API |
| `get_outlook_brief` | Full meeting brief from Outlook calendar (same format as get_meeting_brief) |
| `get_crm_context` | HubSpot CRM: deal stage, lifecycle stage, last contact date, and interaction history |
| `enrich_brief_with_crm` | Meeting brief + HubSpot deal context for sales and partner meetings |
| `debrief_meeting` | Record meeting outcomes, auto-extract action items, draft follow-up email, save to memory |
| `search_meeting_history` | Full-text search across past meetings by person name, topic, company, or date |
| `get_person_history` | Full interaction history with a specific person — all past meetings, commitments, outcomes |
| `get_open_action_items` | All open action items from past meetings with owners, due dates, and meeting context |
| `brief_with_history` | Pre-meeting brief + past interaction history with each attendee from your memory |

### get_upcoming_meetings

```text
Arguments:
  hours_ahead: int = 24    # How far ahead to look (1-168)

Returns:
  List of meetings with id, title, start/end times, attendees, meeting URL
```

### research_attendee

```text
Arguments:
  name: str                # Full name (required)
  company: str = ""        # Company improves accuracy
  context: str = ""        # Any extra context you know

Returns:
  Profile with current_role, company, background, linkedin_summary,
  recent_news[], company_news[], research_sources[]
```

### get_meeting_brief

```text
Arguments:
  meeting_title: str = ""  # Partial title match
  meeting_id: str = ""     # Exact ID from get_upcoming_meetings
  hours_ahead: int = 24

Returns:
  Formatted brief card string
```

### brief_all_today

```text
Arguments: none

Returns:
  Full daily briefing — one card per meeting, attendees researched
  in parallel, each person researched only once even across meetings
```

---

## Configuration

### Microsoft 365 / Outlook Calendar

Register an app in the Azure Portal and set these env vars:

```dotenv
AZURE_CLIENT_ID=your-app-client-id
AZURE_TENANT_ID=common          # "common" works for personal Microsoft accounts
```

On first use, brief-mcp will print a device-code prompt in the terminal. Visit the URL shown, enter the code, and sign in. The token is saved to `~/.brief-mcp/ms_token.json` and refreshed automatically.

**Azure Portal steps (one-time):**
1. Azure Portal → App registrations → New registration
2. Platform: Mobile and desktop applications → `https://login.microsoftonline.com/common/oauth2/nativeclient`
3. API Permissions → Microsoft Graph → Delegated → `Calendars.Read` + `offline_access`
4. Copy the Application (client) ID → set as `AZURE_CLIENT_ID`

### HubSpot CRM

Create a Private App in HubSpot (Settings → Integrations → Private Apps) with scope `crm.objects.contacts.read` and `crm.objects.deals.read`, then:

```dotenv
HUBSPOT_API_KEY=pat-na1-xxxx...    # HubSpot private app token
```

If the key is not set, `get_crm_context` and `enrich_brief_with_crm` return a helpful message rather than crashing.

### Meeting Memory (SQLite)

No configuration required. Memory is stored automatically at `~/.brief-mcp/memory.db` whenever you call `debrief_meeting`. Use `search_meeting_history`, `get_person_history`, and `get_open_action_items` to query it.

---

## Example Prompts

```text
"Brief me for my 2pm meeting."
"Who is Jane Smith from Acme Corp?"
"What should I know before my board presentation today?"
"Research everyone in my next meeting."
"Give me a morning brief for all my meetings today."
"What's the latest news on PartnerCo before my call with them?"
```

---

## Architecture

```text
brief-mcp/
├── server.py              FastMCP server + tool registration
├── models.py              Pydantic v2: Meeting, PersonProfile, MeetingBrief
├── cache.py               TTL cache (cachetools) — 60min / 256 entries
├── tools/
│   ├── calendar_tool.py   get_upcoming_meetings
│   ├── research_tool.py   research_attendee
│   └── brief_tool.py      get_meeting_brief + brief_all_today
└── integrations/
    ├── google_calendar.py  OAuth2 calendar client
    ├── web_search.py       Brave Search + DuckDuckGo fallback
    └── gmail.py            Optional Gmail prior-context enrichment
```

**Key design decisions:**

- **Parallel research** — `asyncio.gather` researches all meeting attendees simultaneously. A 5-person meeting takes the same time as a 1-person meeting.
- **TTL cache** — researching the same person twice in 60 minutes returns instantly from cache. Morning standup + afternoon one-on-one with the same person: only one API call.
- **Graceful degradation** — if Google Calendar is not configured, you can still call `research_attendee` manually. No hard crashes.
- **Deduplicated cross-meeting research** — `brief_all_today` builds a union of all attendees across all meetings, researches each once, then assembles briefs. Efficient even with overlapping attendees.
- **Privacy-first** — all processing is local. Only anonymized name+company queries go outbound to Brave/DuckDuckGo.

---

## Privacy

**Your data never leaves your machine** (except for search queries).

- Google Calendar data is fetched directly via OAuth2 — it never touches any brief-mcp server.
- The only outbound calls are:
  - To Google's Calendar API (authenticated with your personal OAuth token)
  - To Brave Search or DuckDuckGo (query: name + company, no meeting context)
- No telemetry. No analytics. No cloud sync.
- The OAuth token in `~/.brief-mcp/token.json` is read-only.

---

## Full Setup Guide

See [docs/setup.md](docs/setup.md) for:

- Step-by-step Google Cloud Console OAuth2 setup
- Gmail enrichment configuration
- Brave Search API key setup
- Troubleshooting common issues

---

## Roadmap

- [x] Google Calendar integration (OAuth2)
- [x] Parallel attendee research with asyncio.gather
- [x] TTL cache (60 min, 256 entries)
- [x] Brave Search + DuckDuckGo fallback
- [x] Formatted brief card output
- [x] brief_all_today with cross-meeting deduplication
- [x] Optional Gmail prior-email context
- [x] Outlook / Microsoft 365 Calendar support (MSAL device-code flow)
- [x] CRM enrichment — HubSpot contacts, deals, lifecycle stage
- [x] Meeting memory — SQLite FTS5, debrief, action items, interaction history
- [x] brief_with_history — pre-meeting brief + past interaction context
- [ ] LinkedIn official API integration (when available)
- [ ] Salesforce CRM connector
- [ ] Brief as email / Slack message export
- [ ] Voice brief via text-to-speech

---

## Contributing

Contributions are welcome. Please open an issue before submitting a large PR.

```bash
git clone https://github.com/MLDreamer/brief-mcp
cd brief-mcp
uv sync --dev
uv run pytest
uv run ruff check src/ tests/
```

All tests run offline with mocked API responses — no credentials needed for development.

---

## Similar Projects

- [blender-mcp](https://github.com/ahujasid/blender-mcp) — 3D modeling with Claude
- [desktop-commander](https://github.com/wonderwhy-er/DesktopCommanderMCP) — OS control via MCP

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built with [FastMCP](https://github.com/jlowin/fastmcp) and the [Model Context Protocol](https://modelcontextprotocol.io/).*
