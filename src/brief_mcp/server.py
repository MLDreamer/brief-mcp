"""brief-mcp MCP server entry point.

Run directly:
    python -m brief_mcp.server

Or via the CLI script after installation:
    brief-mcp

Or with uvx (no install):
    uvx brief-mcp
"""

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

from .tools.brief_tool import register_brief_tools
from .tools.calendar_tool import register_calendar_tools
from .tools.crm_tool import register_crm_tools
from .tools.debrief_tool import register_debrief_tools
from .tools.outlook_tool import register_outlook_tools
from .tools.research_tool import register_research_tools

# Load .env from the current working directory (or any parent)
load_dotenv()

# Logging setup — respects LOG_LEVEL env var
_log_level = os.getenv("LOG_LEVEL", "WARNING").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.WARNING),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "brief-mcp",
    instructions="""You are a meeting intelligence assistant powered by brief-mcp.

Your job is to help users prepare for meetings, record what happened, and build
a persistent memory of every interaction.

## Available tools

### Pre-meeting prep (Google Calendar)
- **get_upcoming_meetings** — call this first to see what's on the Google Calendar
- **research_attendee(name, company)** — deep-research a single person
- **get_meeting_brief(meeting_title)** — full brief card for one meeting
- **brief_all_today()** — generate briefs for every meeting today (best for morning prep)
- **brief_with_history(meeting_title)** — brief + past interaction history with attendees

### Outlook / Microsoft 365
- **get_outlook_meetings** — upcoming meetings from Outlook calendar
- **get_outlook_brief(meeting_title)** — full brief from Outlook calendar

### CRM (HubSpot)
- **get_crm_context(name, email, company)** — look up a person in HubSpot CRM
- **enrich_brief_with_crm(meeting_title)** — brief + HubSpot deal context

### Post-meeting memory
- **debrief_meeting(meeting_title, notes, action_items, outcomes)** — record outcomes, draft follow-up email
- **search_meeting_history(query)** — search past meetings by person/topic/date
- **get_person_history(name)** — full interaction history with a specific person
- **get_open_action_items()** — all open action items from past meetings

## Recommended flows

Morning prep (Google):
  1. Call brief_all_today() → complete daily briefing in one shot

Before a specific meeting:
  1. Call get_upcoming_meetings() → pick the meeting
  2. Call brief_with_history(meeting_title="...") → brief + past context

Recurring meeting prep:
  1. Call brief_with_history() → shows what was promised/decided last time

After a meeting:
  1. Call debrief_meeting(meeting_title="...", notes="...", action_items="...") → save record + draft email

Sales/partner meeting:
  1. Call enrich_brief_with_crm(meeting_title="...") → brief + HubSpot deal context

## Notes
- All data is processed locally. Only anonymized queries go to search APIs.
- Research results are cached for 60 minutes.
- Meeting memory is stored in ~/.brief-mcp/memory.db (SQLite, fully local).
- Google Calendar, Outlook, and HubSpot integrations each degrade gracefully if not configured.
""",
)

# Register all tools
register_calendar_tools(mcp)
register_research_tools(mcp)
register_brief_tools(mcp)
register_outlook_tools(mcp)
register_crm_tools(mcp)
register_debrief_tools(mcp)

logger.info("brief-mcp server initialized with %d tools", 13)


def main() -> None:
    """Entry point for `brief-mcp` CLI command."""
    mcp.run()


if __name__ == "__main__":
    main()
