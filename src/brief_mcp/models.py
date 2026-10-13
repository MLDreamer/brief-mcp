"""Pydantic v2 models for brief-mcp data structures."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Attendee(BaseModel):
    """A single meeting attendee."""

    name: str
    email: Optional[str] = None
    is_organizer: bool = False

    def display_name(self) -> str:
        """Return a human-readable name, falling back to email local-part."""
        if self.name:
            return self.name
        if self.email:
            return self.email.split("@")[0].replace(".", " ").title()
        return "Unknown"


class Meeting(BaseModel):
    """A single calendar event / meeting."""

    id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: list[Attendee] = Field(default_factory=list)
    location: Optional[str] = None
    description: Optional[str] = None
    meeting_url: Optional[str] = None
    calendar_link: Optional[str] = None

    @property
    def duration_minutes(self) -> int:
        """Return meeting duration in minutes."""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    @property
    def external_attendees(self) -> list[Attendee]:
        """Return attendees who are not the calendar owner (non-organizer)."""
        return [a for a in self.attendees if not a.is_organizer]


class PersonProfile(BaseModel):
    """Researched profile for a meeting attendee."""

    name: str
    current_role: Optional[str] = None
    company: Optional[str] = None
    linkedin_summary: Optional[str] = None
    recent_news: list[str] = Field(default_factory=list)
    company_news: list[str] = Field(default_factory=list)
    background: Optional[str] = None
    research_timestamp: datetime = Field(default_factory=datetime.now)
    research_sources: list[str] = Field(default_factory=list)

    def cache_key(self) -> str:
        """Generate a cache key for this profile."""
        name_slug = self.name.lower().replace(" ", "_")
        company_slug = (self.company or "").lower().replace(" ", "_")
        return f"{name_slug}__{company_slug}"


class MeetingBrief(BaseModel):
    """Complete pre-meeting intelligence brief."""

    meeting: Meeting
    attendee_profiles: list[PersonProfile] = Field(default_factory=list)
    talking_points: list[str] = Field(default_factory=list)
    watch_outs: list[str] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)

    def format_card(self) -> str:
        """Return the brief as a formatted, readable card string."""
        lines: list[str] = []
        sep = "=" * 60

        lines.append(sep)
        lines.append(f"  MEETING BRIEF: {self.meeting.title.upper()}")
        lines.append(sep)

        # Meeting metadata
        start = self.meeting.start_time.strftime("%A, %B %d %Y at %I:%M %p")
        lines.append(f"\n  When    : {start}")
        lines.append(f"  Duration: {self.meeting.duration_minutes} minutes")
        if self.meeting.location:
            lines.append(f"  Where   : {self.meeting.location}")
        if self.meeting.meeting_url:
            lines.append(f"  Link    : {self.meeting.meeting_url}")

        # Attendees quick list
        if self.meeting.attendees:
            names = ", ".join(a.display_name() for a in self.meeting.attendees)
            lines.append(f"\n  Attendees ({len(self.meeting.attendees)}): {names}")

        # Attendee profiles
        if self.attendee_profiles:
            lines.append("\n" + "-" * 60)
            lines.append("  ATTENDEE PROFILES")
            lines.append("-" * 60)
            for profile in self.attendee_profiles:
                lines.append(f"\n  >> {profile.name}")
                if profile.current_role and profile.company:
                    lines.append(f"     Role    : {profile.current_role} @ {profile.company}")
                elif profile.current_role:
                    lines.append(f"     Role    : {profile.current_role}")
                elif profile.company:
                    lines.append(f"     Company : {profile.company}")
                if profile.background:
                    lines.append(f"     Bio     : {profile.background}")
                if profile.linkedin_summary:
                    lines.append(f"     LinkedIn: {profile.linkedin_summary}")
                if profile.recent_news:
                    lines.append("     Recent  :")
                    for item in profile.recent_news[:3]:
                        lines.append(f"       - {item}")
                if profile.company_news:
                    lines.append("     Co News :")
                    for item in profile.company_news[:2]:
                        lines.append(f"       - {item}")

        # Talking points
        if self.talking_points:
            lines.append("\n" + "-" * 60)
            lines.append("  SUGGESTED TALKING POINTS")
            lines.append("-" * 60)
            for i, point in enumerate(self.talking_points, 1):
                lines.append(f"  {i}. {point}")

        # Watch-outs
        if self.watch_outs:
            lines.append("\n" + "-" * 60)
            lines.append("  WATCH-OUTS / SENSITIVITIES")
            lines.append("-" * 60)
            for item in self.watch_outs:
                lines.append(f"  ! {item}")

        # Context notes
        if self.context_notes:
            lines.append("\n" + "-" * 60)
            lines.append("  CONTEXT NOTES")
            lines.append("-" * 60)
            for note in self.context_notes:
                lines.append(f"  * {note}")

        lines.append(f"\n  Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(sep)

        return "\n".join(lines)


class ResearchRequest(BaseModel):
    """Input for a person research request."""

    name: str
    company: str = ""
    context: str = ""


class BriefRequest(BaseModel):
    """Input for generating a meeting brief."""

    meeting_title: str = ""
    meeting_id: str = ""
    hours_ahead: int = 24
