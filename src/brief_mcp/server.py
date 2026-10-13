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

Your job is to help users prepare for meetings by researching attendees and
generating executive briefing cards.

## Available tools

- **get_upcoming_meetings** — call this first to see what's on the calendar
- **research_attendee(name, company)** — deep-research a single person
- **get_meeting_brief(meeting_title)** — full brief card for one meeting
- **brief_all_today()** — generate briefs for every meeting today (best for morning prep)

## Recommended flows

Morning prep:
  1. Call brief_all_today() → get a complete daily briefing in one shot

Before a specific meeting:
  1. Call get_upcoming_meetings() → pick the meeting
  2. Call get_meeting_brief(meeting_title="...") → get the brief

Ad-hoc research:
  1. Call research_attendee(name="Jane Smith", company="Acme Corp")

## Notes
- All data is processed locally. Only anonymized queries go to search APIs.
- Research results are cached for 60 minutes. Force a refresh by providing context.
- If Google Calendar is not configured, you can still research individuals manually.
""",
)

# Register all tools
register_calendar_tools(mcp)
register_research_tools(mcp)
register_brief_tools(mcp)

logger.info("brief-mcp server initialized with %d tools", 4)


def main() -> None:
    """Entry point for `brief-mcp` CLI command."""
    mcp.run()


if __name__ == "__main__":
    main()
