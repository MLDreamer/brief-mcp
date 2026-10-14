# brief-mcp

> **Know everyone in the room before you walk in.**

[![PyPI version](https://img.shields.io/pypi/v/brief-mcp?color=0066CC&label=PyPI)](https://pypi.org/project/brief-mcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-0066CC)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-7c3aed)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-123%20passing-22c55e)](#)
[![CI](https://github.com/MLDreamer/brief-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MLDreamer/brief-mcp/actions)
[![Glama](https://glama.ai/mcp/servers/MLDreamer/brief-mcp/badges/score.svg)](https://glama.ai/mcp/servers/MLDreamer/brief-mcp)

**brief-mcp** is the first open-source [Model Context Protocol](https://modelcontextprotocol.io/) server for meeting intelligence. It connects Claude — and any MCP-compatible AI assistant — to your calendar, the web, your CRM, and your own meeting history, then generates executive-grade briefing cards in seconds.

No browser tabs. No LinkedIn spelunking. No manual prep.

---

## Table of Contents

- [What it does](#what-it-does)
- [Demo](#demo)
- [Why brief-mcp is different](#why-brief-mcp-is-different)
- [Install](#install)
- [Quick Start](#quick-start)
- [Client Configuration](#client-configuration)
  - [Claude Desktop](#claude-desktop)
  - [VS Code / Cursor](#vs-code--cursor)
  - [Zed](#zed)
- [Integrations](#integrations)
  - [Google Calendar](#google-calendar)
  - [Microsoft 365 / Outlook](#microsoft-365--outlook)
  - [HubSpot CRM](#hubspot-crm)
  - [Web Research](#web-research)
  - [Meeting Memory](#meeting-memory)
- [All 13 Tools](#all-13-tools)
  - [Pre-Meeting: Google Calendar](#pre-meeting-google-calendar)
  - [Pre-Meeting: Microsoft 365](#pre-meeting-microsoft-365)
  - [CRM Enrichment](#crm-enrichment)
  - [Post-Meeting Memory](#post-meeting-memory)
- [Usage Flows](#usage-flows)
- [Architecture](#architecture)
- [Privacy](#privacy)
- [Contributing](#contributing)
- [Roadmap](#roadmap)
- [License](#license)

---

## What it does

brief-mcp gives your AI assistant five capabilities it doesn't have out of the box:

| Capability | What it means |
| --- | --- |
| **Pre-meeting research** | Reads your calendar, looks up every attendee on the web, and assembles a briefing card — who they are, what their company is doing, what to say |
| **Dual calendar support** | Works with both Google Calendar (OAuth2) and Microsoft 365 / Outlook (Microsoft Graph) |
| **CRM enrichment** | Pulls HubSpot deal stage, lifecycle, and last-contact data into the brief for sales and partner meetings |
| **Post-meeting memory** | After a meeting, record what happened — auto-extract action items, draft the follow-up email, and save everything to a local SQLite database |
| **Persistent history** | Before your next meeting with the same person, brief-mcp shows you everything that was said, promised, and decided before — building a relationship memory you actually own |

---

## Demo

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
  WATCH-OUTS / SENSITIVITIES
------------------------------------------------------------
  ! Series B funding may prompt renegotiation — know your commercial floor.
  ! Carol joined in 2026 — bring her up to speed on integration history.

  Generated: 2026-10-13 09:14
============================================================
```

Or for a returning customer meeting:

```text
------------------------------------------------------------
  PAST INTERACTION HISTORY — Bob Patel
------------------------------------------------------------
  * Met 2026-07-18 — Product roadmap sync
    Committed: "Send updated API latency benchmarks by Aug 1"
    Status: Follow-up sent ✓

  * Met 2026-09-02 — Q3 review
    Committed: "Schedule infra deep-dive with their SRE team"
    Status: OPEN — 41 days outstanding

  Open action items from past meetings: 1
------------------------------------------------------------
```

All of that from a single prompt. No switching tools, no browser tabs.

---

## Why brief-mcp is different

### The only meeting intelligence MCP server

As of October 2026, brief-mcp is the **only open-source MCP server** dedicated to meeting preparation, CRM enrichment, and post-meeting memory. A GitHub-wide search returns zero competing implementations.

### End-to-end meeting lifecycle

Most tools address one phase. brief-mcp covers all three:

```
Before  →  During context  →  After
─────────────────────────────────────────────────────────
Brief      Who's in the room,   Debrief, action items,
calendar   news, CRM context,   follow-up email, memory,
           past history         open item tracking
```

### Dual-calendar: Google + Microsoft 365

Supports both ecosystems with separate OAuth2 flows — Google Calendar via the Workspace API and Outlook via Microsoft Graph (MSAL device-code, headless-friendly). Most professionals use one or the other; brief-mcp supports both from one server.

### Persistent relationship memory

brief-mcp builds a local SQLite database (with FTS5 full-text search) of every meeting you record. Before a repeat meeting, `brief_with_history` surfaces:

- Every past meeting with that person
- Commitments made and whether they were fulfilled
- Topics that recur across sessions
- How many days outstanding open action items have been sitting

No SaaS subscription. No cloud sync. Fully yours.

### Engineered for correctness

- **Parallel async research** — `asyncio.gather` fires all attendee lookups simultaneously; a 6-person meeting takes the same wall-clock time as a 1-person meeting
- **Timezone-correct everywhere** — Microsoft Graph timezone strings resolved via `ZoneInfo` IANA and Windows→IANA mapping; all datetimes are timezone-aware throughout
- **TTL cache** — 60-minute, 256-entry cache with dual-indexing (name+company and name-only) prevents cache misses when calendar lookups don't have company context
- **Full pagination** — Google Calendar and Microsoft Graph results are paginated; no silent truncation at 25 items
- **123 tests, all offline** — every integration is mocked; no credentials needed to run the full suite

---

## Install

### Zero-install (recommended)

```bash
uvx brief-mcp
```

`uvx` runs brief-mcp in an isolated environment without a permanent install. Requires [uv](https://docs.astral.sh/uv/).

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

**Step 1 — Enable Google Calendar** (5 minutes, one-time):

Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Enable **Google Calendar API** → Credentials → Create **OAuth 2.0 Client ID** (Desktop app) → Download JSON.

**Step 2 — Create `.env`** in your working directory:

```dotenv
# Required for Google Calendar
GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json

# Optional but recommended — free tier at brave.com/search/api
BRAVE_API_KEY=BSAxxx...

# Optional — Microsoft 365 / Outlook
AZURE_CLIENT_ID=your-azure-app-client-id
AZURE_TENANT_ID=common

# Optional — HubSpot CRM
HUBSPOT_API_KEY=pat-na1-xxxx...
```

**Step 3 — Configure your AI client** (see section below).

**Step 4 — Open Claude and say:**

```
"Brief me for today's meetings."
```

On first run, a browser window opens for Google OAuth consent. After that, fully silent.

---

## Client Configuration

### Claude Desktop

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "brief-mcp": {
      "command": "uvx",
      "args": ["brief-mcp"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "/Users/you/credentials.json",
        "BRAVE_API_KEY": "BSAxxx...",
        "AZURE_CLIENT_ID": "your-client-id",
        "HUBSPOT_API_KEY": "pat-na1-xxxx..."
      }
    }
  }
}
```

Restart Claude Desktop after saving.

### VS Code / Cursor

Create `.vscode/mcp.json` in your workspace root:

```json
{
  "servers": {
    "brief-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["brief-mcp"],
      "env": {
        "GOOGLE_CREDENTIALS_PATH": "${workspaceFolder}/credentials.json",
        "BRAVE_API_KEY": "BSAxxx...",
        "HUBSPOT_API_KEY": "pat-na1-xxxx..."
      }
    }
  }
}
```

### Zed

In `~/.config/zed/settings.json`:

```json
{
  "assistant": {
    "mcp_servers": {
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
}
```

---

## Integrations

### Google Calendar

**Auth:** OAuth2 desktop flow via `google-auth-oauthlib`. Token stored at `~/.brief-mcp/token.json` and refreshed silently.

**Required env var:** `GOOGLE_CREDENTIALS_PATH` — path to the JSON file downloaded from Google Cloud Console.

**Scopes used:** `calendar.readonly` (optionally `gmail.readonly` for prior-email context).

**Graceful degradation:** If not configured, all Google Calendar tools return a clear message and continue working — `research_attendee` functions without any calendar.

### Microsoft 365 / Outlook

**Auth:** MSAL device-code flow — headless-friendly, works in any terminal. Token stored at `~/.brief-mcp/ms_token.json` and auto-refreshed.

**Required env vars:**

```dotenv
AZURE_CLIENT_ID=your-app-client-id
AZURE_TENANT_ID=common          # "common" = personal + work accounts
```

**Azure Portal setup (one-time, 3 minutes):**

1. [Azure Portal](https://portal.azure.com) → App registrations → **New registration**
2. Supported account types: *Accounts in any organizational directory and personal Microsoft accounts*
3. Redirect URI → Platform: **Mobile and desktop** → `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. API Permissions → Microsoft Graph → Delegated → add `Calendars.Read` + `offline_access` → Grant admin consent
5. Copy **Application (client) ID** → set as `AZURE_CLIENT_ID`

On first run, brief-mcp prints:

```
To sign in, visit https://microsoft.com/devicelogin and enter code: ABCD1234
```

After sign-in, all subsequent runs are silent.

**Timezone handling:** Microsoft Graph returns naive datetime strings with a separate `timeZone` field. brief-mcp resolves this using Python's `zoneinfo` for IANA names and a built-in Windows→IANA mapping for timezones like `"Eastern Standard Time"`.

### HubSpot CRM

**Auth:** Private app token (no OAuth callback required).

**Required env var:** `HUBSPOT_API_KEY`

**HubSpot setup (5 minutes):**

1. HubSpot → Settings → Integrations → **Private Apps** → Create a private app
2. Scopes: `crm.objects.contacts.read` + `crm.objects.deals.read`
3. Generate token → copy → set as `HUBSPOT_API_KEY`

**What it fetches:** Contact name, email, job title, company, lifecycle stage, last contacted date, and all associated deals (name, stage, amount, close date).

**Graceful degradation:** If `HUBSPOT_API_KEY` is not set, CRM tools return a helpful setup message instead of crashing.

### Web Research

**Primary:** [Brave Search API](https://brave.com/search/api/) — set `BRAVE_API_KEY` for best results (free tier available, 2,000 queries/month).

**Fallback:** DuckDuckGo HTML endpoint — works with no configuration, no API key required. brief-mcp automatically falls back if Brave is not configured.

**What it does per person:** Fires 3 parallel searches — general bio, LinkedIn profile, and company news — then extracts current role, company, recent news headlines, and background from the combined results.

### Meeting Memory

**No configuration required.** Memory is stored automatically at `~/.brief-mcp/memory.db` — a local SQLite database using FTS5 full-text search.

The database stores:

- Meeting records (title, date, attendees, summary, action items, outcomes)
- Per-person interaction history (topics discussed, sentiment, commitments)
- Action item status with per-item completion tracking

Data never leaves your machine.

---

## All 13 Tools

### Pre-Meeting: Google Calendar

#### `get_upcoming_meetings`

Reads your Google Calendar and returns all meetings in the next N hours.

```text
Arguments:
  hours_ahead: int = 24     # Look-ahead window in hours (max: 168 / 1 week)

Returns:
  List of meetings, each with:
  - id, title, start_time, end_time (timezone-aware)
  - attendees: [{name, email, is_organizer}]
  - meeting_url (Google Meet, Zoom, or Teams link if present)
  - location, description, calendar_link
```

#### `research_attendee`

Researches a single person via parallel web search. Results are cached for 60 minutes.

```text
Arguments:
  name: str           # Full name (required)
  company: str = ""   # Company name — improves search accuracy significantly
  context: str = ""   # Any extra context you know about this person

Returns:
  PersonProfile with:
  - current_role, company, background, linkedin_summary
  - recent_news[]    — recent headlines about this person
  - company_news[]   — recent headlines about their company
  - research_sources[]
```

#### `get_meeting_brief`

Looks up a meeting from your calendar and generates a full brief — attendee profiles, talking points, and watch-outs — all researched in parallel.

```text
Arguments:
  meeting_title: str = ""   # Partial title match (case-insensitive)
  meeting_id: str = ""      # Exact ID from get_upcoming_meetings (takes priority)
  hours_ahead: int = 24

Returns:
  Formatted brief card as a multi-line string.
  Returns an error with available meeting titles if no match found.
```

#### `brief_all_today`

Generates briefs for every meeting on today's calendar. Deduplicates attendee research across meetings — if the same person appears in your 10am and 3pm, they are researched exactly once.

```text
Arguments: none

Returns:
  Full daily briefing — one card per meeting, separated by dividers.
  Header shows total meeting count and date.
```

#### `brief_with_history`

Same as `get_meeting_brief` but enriched with past interaction history from your local meeting memory. Shows what was discussed, committed, and decided in every prior meeting with each attendee.

```text
Arguments:
  meeting_title: str = ""
  meeting_id: str = ""
  hours_ahead: int = 24

Returns:
  Standard brief card + past interaction section per attendee.
  Shows open action items, recurring topics, and commitment status.
```

---

### Pre-Meeting: Microsoft 365

#### `get_outlook_meetings`

Reads your Outlook / Microsoft 365 calendar via Microsoft Graph. Returns the same format as `get_upcoming_meetings`.

```text
Arguments:
  hours_ahead: int = 24

Returns:
  Same format as get_upcoming_meetings.
  Requires AZURE_CLIENT_ID in env.
```

#### `get_outlook_brief`

Generates a full brief from your Outlook calendar. Identical output format to `get_meeting_brief`.

```text
Arguments:
  meeting_title: str = ""
  meeting_id: str = ""
  hours_ahead: int = 24

Returns:
  Formatted brief card string.
```

---

### CRM Enrichment

#### `get_crm_context`

Looks up a person in HubSpot CRM and returns their contact record and associated deals.

```text
Arguments:
  name: str           # Full name
  email: str = ""     # Email address — used for exact-match lookup if provided
  company: str = ""   # Company name — improves search when name is common

Returns:
  Formatted CRM summary:
  - Name, job title, company, lifecycle stage
  - Last contacted date
  - All associated deals: name, stage, amount, close date
  Returns "No CRM record found for {name}" if not found.
```

#### `enrich_brief_with_crm`

Generates a standard meeting brief then appends a CRM section for every attendee found in HubSpot. Ideal for sales and partner meetings.

```text
Arguments:
  meeting_title: str   # Matches against Google Calendar

Returns:
  Full brief card + CRM CONTEXT section at the bottom.
  Shows deal pipeline, stage, amount, and last activity per attendee.
```

---

### Post-Meeting Memory

#### `debrief_meeting`

Records what happened in a meeting. Saves to the local SQLite database, auto-extracts action items from free-form notes, and drafts a follow-up email.

```text
Arguments:
  meeting_title: str      # Matches the calendar event (looks back 24h + ahead 2h)
  notes: str              # Raw meeting notes — bullet points, transcript, anything
  action_items: str = ""  # Comma-separated tasks (e.g. "Alice to send report, Bob to schedule demo")
  outcomes: str = ""      # What was decided or agreed

Returns:
  Formatted debrief card:
  - Structured meeting record saved to memory.db
  - Extracted action items with inferred owners and due dates
  - Draft follow-up email ready to send
  - Next-step suggestions

Action item extraction recognises:
  "ACTION: ..."  "TODO: ..."  "FOLLOW-UP: ..."
  "- [ ] ..."    "* [ ] ..."
```

#### `search_meeting_history`

Full-text search across all past meetings using SQLite FTS5. Searches meeting title, attendees, summary, action items, and outcomes simultaneously.

```text
Arguments:
  query: str        # Keyword, person name, company, topic, or date
  limit: int = 10

Returns:
  Formatted list of matching meetings with date, attendees, summary, and action items.
  Returns "No matching meetings found" if empty.
```

#### `get_person_history`

Returns the complete interaction history with a specific person — every meeting, every topic, every commitment, in chronological order.

```text
Arguments:
  name: str         # Person's name (partial match supported)

Returns:
  Chronological timeline of all meetings with this person:
  - Meeting date, title, topics discussed
  - Commitments made (by you and by them)
  - Action item status (open / closed / how many days outstanding)
```

#### `get_open_action_items`

Lists every open action item across all past meetings, with owner, meeting context, and how long it has been outstanding.

```text
Arguments: none

Returns:
  Sorted list of open action items:
  - Task description
  - Owner (if detected from notes)
  - Source meeting title and date
  - Days since the meeting
  Returns "No open action items" if all tasks are complete.
```

---

## Usage Flows

### Morning briefing

```
"Give me a morning brief for all my meetings today."
```

brief-mcp calls `brief_all_today()` — reads your calendar, researches every attendee in parallel (each person once, even across overlapping meetings), and returns one formatted card per meeting. Typical time for a 5-meeting day with 12 unique attendees: under 8 seconds.

### Before a specific meeting

```
"Brief me for the Q4 review with PartnerCo at 2pm."
```

Use `brief_with_history` for recurring meetings — it adds a full history section showing everything said and committed in prior sessions with those same people.

### After a meeting

```
"Debrief the Q4 review. Notes: discussed roadmap integration, 
Bob will send technical spec by Oct 20, Carol to set up infra call.
Outcomes: agreed on Phase 2 timeline."
```

brief-mcp:
- Saves the meeting record to `~/.brief-mcp/memory.db`
- Extracts action items: *Bob → send technical spec by Oct 20*, *Carol → set up infra call*
- Drafts a follow-up email with the agreed outcomes and next steps
- Next time you meet Bob or Carol, `brief_with_history` will surface this record

### Sales meeting with CRM context

```
"Enrich the brief for my Salesforce call with deal context from HubSpot."
```

`enrich_brief_with_crm` adds a CRM section showing the deal name, stage, amount, and last activity date for every attendee found in HubSpot — giving you the commercial picture alongside the personal one.

### Ad-hoc person research

```
"Who is Priya Mehta from Infosys?"
```

`research_attendee("Priya Mehta", "Infosys")` — runs in under 3 seconds, cached for 60 minutes.

### Checking outstanding commitments

```
"What's still open from my meetings this week?"
```

`get_open_action_items()` scans the memory database and returns every unresolved task with owner, source meeting, and how long it has been outstanding.

---

## Architecture

```text
brief-mcp/
├── server.py                   FastMCP server — registers all 13 tools
├── models.py                   Pydantic v2 models (Meeting, PersonProfile, MeetingBrief)
├── cache.py                    TTL cache — 60 min / 256 entries, dual-indexed
├── memory.py                   SQLite + FTS5 meeting memory database
│
├── integrations/
│   ├── google_calendar.py      Google Calendar OAuth2 client
│   ├── outlook_calendar.py     Microsoft Graph MSAL client + timezone resolution
│   ├── web_search.py           Brave Search + DuckDuckGo fallback (3 parallel queries)
│   ├── hubspot.py              HubSpot CRM REST client
│   └── gmail.py                Optional Gmail prior-email context
│
└── tools/
    ├── _shared.py              Shared helpers (_find_meeting, _research_attendee_with_cache)
    ├── calendar_tool.py        get_upcoming_meetings
    ├── research_tool.py        research_attendee
    ├── brief_tool.py           get_meeting_brief + brief_all_today + helpers
    ├── outlook_tool.py         get_outlook_meetings + get_outlook_brief
    ├── crm_tool.py             get_crm_context + enrich_brief_with_crm
    └── debrief_tool.py         debrief_meeting + memory tools (5 tools)
```

### Key design decisions

**Parallel async research.** `asyncio.gather` fires all attendee lookups simultaneously. A meeting with 6 attendees takes the same wall-clock time as a meeting with 1. `brief_all_today` deduplicates across meetings first, then fires a single gather across all unique attendees for the day.

**Dual-indexed TTL cache.** Profiles are stored under both `name+company` and `name-only` keys. When the calendar fires lookups without company context (the common case), it still hits profiles stored by the user with explicit company. 60-minute TTL, 256-entry LRU.

**Timezone-correct datetimes.** Google Calendar returns ISO 8601 strings (timezone-aware). Microsoft Graph returns naive strings with a separate `timeZone` field (which may be an IANA name or a Windows display name). brief-mcp resolves both via `zoneinfo.ZoneInfo` and a built-in Windows→IANA mapping. All internal datetimes are `timezone.utc`-aware.

**FTS5 full-text search.** Meeting memory uses SQLite's built-in FTS5 extension — no external search dependency. The UPDATE trigger is implemented as DELETE + INSERT (FTS5 does not support UPDATE statements). Search covers title, attendees, summary, action items, and outcomes simultaneously.

**Per-item action tracking.** `mark_action_done` supports both item-level completion (stores completed item text in a JSON column) and meeting-level closure (`follow_up_sent`). `get_open_action_items` filters out completed items per meeting.

**Graceful degradation everywhere.** Every integration checks for its required env var at call time. Missing credentials return a clear setup message — the server never crashes, and unconfigured integrations don't affect configured ones.

---

## Privacy

**All processing is local. Your meetings, notes, and history never leave your machine.**

| Data | Where it goes |
| --- | --- |
| Calendar events | Fetched directly from Google / Microsoft via your personal OAuth token. Never touches any brief-mcp server. |
| Attendee research | Name + company sent to Brave Search or DuckDuckGo. No meeting context, no email addresses, no calendar data. |
| Meeting memory | Stored in `~/.brief-mcp/memory.db` on your local machine. Never synced anywhere. |
| HubSpot data | Fetched directly from HubSpot using your private app token. |
| OAuth tokens | Stored at `~/.brief-mcp/token.json` and `~/.brief-mcp/ms_token.json`. Read-only scopes only. |

**No telemetry. No analytics. No cloud sync. No accounts.**

---

## Contributing

Pull requests are welcome. Please open an issue to discuss significant changes before starting.

### Development setup

```bash
git clone https://github.com/MLDreamer/brief-mcp
cd brief-mcp
uv sync --dev
```

### Running tests

All 123 tests run offline — no credentials required.

```bash
uv run pytest                          # full suite
uv run pytest tests/test_memory.py    # specific module
uv run pytest -v --tb=short           # verbose output
```

### Linting

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Test coverage

| Module | Tests | Coverage |
| --- | --- | --- |
| `memory.py` | 22 | SQLite CRUD, FTS5 search, person history, per-item action tracking |
| `integrations/hubspot.py` | 11 | Contact search, deal fetch, no-key degradation, 401 handling |
| `integrations/outlook_calendar.py` | 11 | Timezone resolution, Teams URL, all-day events, pagination |
| `tools/debrief_tool.py` | 23 | All 5 debrief tools, action item extraction, memory integration |
| `tools/crm_tool.py` | 8 | CRM tools, no-key paths, brief enrichment |
| `cache.py` | 15 | Dual-index lookup, configure, invalidate, stats |
| `tools/` (core) | 33 | Brief generation, deduplication, timezone-awareness, error paths |

---

## Roadmap

### Shipped

- [x] Google Calendar — OAuth2, full pagination, Meet/Zoom/Teams URL extraction
- [x] Microsoft 365 / Outlook — MSAL device-code, Windows timezone mapping, pagination
- [x] Web research — Brave Search + DuckDuckGo fallback, 3 parallel queries per person
- [x] Parallel async research with `asyncio.gather` + TTL cache
- [x] HubSpot CRM — contact search, deal pipeline, lifecycle stage
- [x] `brief_all_today` with cross-meeting attendee deduplication
- [x] Post-meeting debrief — action item extraction, follow-up email draft
- [x] SQLite FTS5 meeting memory — search, person history, action item tracking
- [x] `brief_with_history` — pre-meeting brief + full past interaction context
- [x] Optional Gmail prior-email context enrichment
- [x] 123 tests (all offline, all passing)

### Planned

- [ ] Salesforce CRM connector
- [ ] Slack — post brief or debrief to a channel
- [ ] LinkedIn data via official API (when available)
- [ ] Automatic follow-up email sending (Gmail / Outlook)
- [ ] Voice brief via text-to-speech
- [ ] Team shared memory (multi-user SQLite / shared drive)
- [ ] Apollo.io / People Data Labs for enriched professional profiles

---

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=MLDreamer/brief-mcp&type=Date)](https://star-history.com/#MLDreamer/brief-mcp&Date)

---

## Similar Projects

- [blender-mcp](https://github.com/ahujasid/blender-mcp) — AI controls Blender 3D
- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) — AI-powered code intelligence

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built on [FastMCP](https://github.com/jlowin/fastmcp) and the [Model Context Protocol](https://modelcontextprotocol.io/).*

*If brief-mcp saves you time before a meeting, consider starring the repo — it helps others find it.*
