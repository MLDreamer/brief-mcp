"""HubSpot CRM connector for brief-mcp.

Uses the HubSpot CRM REST API v3 directly via httpx (no heavy SDK).

Required env var:
    HUBSPOT_API_KEY — HubSpot private app token (Settings → Integrations → Private Apps)

Graceful degradation: if HUBSPOT_API_KEY is not set, all functions return
None / empty strings rather than raising exceptions.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_HUBSPOT_BASE = "https://api.hubapi.com"


# ── Models ────────────────────────────────────────────────────────────────────


class HubSpotDeal(BaseModel):
    """A HubSpot deal record."""

    name: str
    stage: Optional[str] = None
    amount: Optional[float] = None
    close_date: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class HubSpotContact(BaseModel):
    """A HubSpot contact record with associated deals."""

    name: str
    email: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    last_contacted: Optional[datetime] = None
    notes: list[str] = Field(default_factory=list)
    deals: list[HubSpotDeal] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_api_key() -> str:
    return os.getenv("HUBSPOT_API_KEY", "")


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _parse_hs_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse a HubSpot ISO datetime string (may be epoch-ms string or ISO)."""
    if not value:
        return None
    # HubSpot sometimes returns epoch milliseconds as strings
    try:
        if value.isdigit():
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(value.rstrip("Z"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OSError) as exc:
        logger.debug("Could not parse HubSpot datetime '%s': %s", value, exc)
        return None


def _parse_contact(contact_obj: dict) -> Optional[HubSpotContact]:
    """Convert a HubSpot contact API object to HubSpotContact."""
    props = contact_obj.get("properties", {})

    first = props.get("firstname", "") or ""
    last = props.get("lastname", "") or ""
    name = f"{first} {last}".strip() or props.get("email", "Unknown")

    email = props.get("email") or None
    company = props.get("company") or None
    job_title = props.get("jobtitle") or None
    phone = props.get("phone") or None
    lifecycle_stage = props.get("lifecyclestage") or None
    last_contacted = _parse_hs_datetime(props.get("notes_last_contacted"))
    # notes: fetched via /crm/v4/objects/notes associations — not yet implemented

    return HubSpotContact(
        name=name,
        email=email,
        company=company,
        job_title=job_title,
        phone=phone,
        lifecycle_stage=lifecycle_stage,
        last_contacted=last_contacted,
        # notes left as default [] — association fetch not yet implemented
    )


def _parse_deal(deal_obj: dict) -> HubSpotDeal:
    """Convert a HubSpot deal API object to HubSpotDeal."""
    props = deal_obj.get("properties", {})
    name = props.get("dealname", "") or "Unnamed Deal"
    stage = props.get("dealstage") or None
    amount_str = props.get("amount")
    amount: Optional[float] = None
    if amount_str:
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            pass
    close_date = _parse_hs_datetime(props.get("closedate"))
    last_activity = _parse_hs_datetime(props.get("notes_last_updated"))

    return HubSpotDeal(
        name=name,
        stage=stage,
        amount=amount,
        close_date=close_date,
        last_activity=last_activity,
    )


# ── API calls ─────────────────────────────────────────────────────────────────


async def _search_contacts_api(
    client: httpx.AsyncClient,
    filters: list[dict],
    limit: int = 5,
) -> list[dict]:
    """POST to HubSpot contacts search endpoint and return raw contact objects."""
    payload = {
        "filterGroups": [{"filters": filters}],
        "properties": [
            "firstname",
            "lastname",
            "email",
            "company",
            "jobtitle",
            "phone",
            "lifecyclestage",
            "notes_last_contacted",
        ],
        "limit": limit,
    }
    try:
        response = await client.post(
            f"{_HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers=_auth_headers(),
            json=payload,
        )
        response.raise_for_status()
        return response.json().get("results", [])
    except httpx.HTTPStatusError as exc:
        logger.warning("HubSpot contacts search error %s: %s", exc.response.status_code, exc.response.text[:200])
        return []
    except Exception as exc:
        logger.warning("HubSpot contacts search failed: %s", exc)
        return []


async def _get_contact_deals(client: httpx.AsyncClient, contact_id: str) -> list[HubSpotDeal]:
    """Fetch deals associated with a contact ID."""
    try:
        resp = await client.get(
            f"{_HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}/associations/deals",
            headers=_auth_headers(),
        )
        resp.raise_for_status()
        deal_assocs = resp.json().get("results", [])
    except Exception as exc:
        logger.debug("Could not fetch deals for contact %s: %s", contact_id, exc)
        return []

    deals: list[HubSpotDeal] = []
    for assoc in deal_assocs[:10]:  # cap at 10 deals
        deal_id = assoc.get("id")
        if not deal_id:
            continue
        try:
            deal_resp = await client.get(
                f"{_HUBSPOT_BASE}/crm/v3/objects/deals/{deal_id}",
                headers=_auth_headers(),
                params={
                    "properties": "dealname,dealstage,amount,closedate,notes_last_updated"
                },
            )
            deal_resp.raise_for_status()
            deals.append(_parse_deal(deal_resp.json()))
        except Exception as exc:
            logger.debug("Could not fetch deal %s: %s", deal_id, exc)

    return deals


# ── Public API ────────────────────────────────────────────────────────────────


async def search_contact(
    name: str = "",
    email: str = "",
    company: str = "",
) -> Optional[HubSpotContact]:
    """Search HubSpot for a contact by email, name, or company.

    Tries email exact-match first (most reliable), then full-name contains search.
    Fetches associated deals and appends them to the returned HubSpotContact.

    Returns None (not raises) if no contact is found or HUBSPOT_API_KEY is not set.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning(
            "HUBSPOT_API_KEY not set — HubSpot CRM integration disabled. "
            "Set HUBSPOT_API_KEY in your .env to enable."
        )
        return None

    raw_contacts: list[dict] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        # 1. Email exact match
        if email:
            raw_contacts = await _search_contacts_api(
                client,
                filters=[{"propertyName": "email", "operator": "EQ", "value": email}],
            )

        # 2. Name contains search (first name or last name)
        if not raw_contacts and name:
            parts = name.strip().split()
            if parts:
                filters = []
                if len(parts) >= 2:
                    # Try firstname + lastname combination
                    filters = [
                        {"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": parts[0]},
                        {"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": parts[-1]},
                    ]
                else:
                    filters = [
                        {"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": parts[0]},
                    ]
                raw_contacts = await _search_contacts_api(client, filters)

        # 3. Fallback: company name search if still nothing
        if not raw_contacts and company:
            raw_contacts = await _search_contacts_api(
                client,
                filters=[{"propertyName": "company", "operator": "CONTAINS_TOKEN", "value": company}],
            )

        if not raw_contacts:
            return None

        raw = raw_contacts[0]
        contact = _parse_contact(raw)
        if contact is None:
            return None

        contact_id = raw.get("id", "")
        if contact_id:
            contact.deals = await _get_contact_deals(client, contact_id)

    return contact


async def get_crm_context(name: str, email: str = "", company: str = "") -> str:
    """Return a readable CRM summary string for a named person.

    Calls search_contact, formats the HubSpotContact as a brief narrative.
    Returns a "No CRM record found" message if the person is not in HubSpot.
    """
    contact = await search_contact(name=name, email=email, company=company)

    if contact is None:
        api_key = _get_api_key()
        if not api_key:
            return (
                f"CRM context unavailable for {name}: HUBSPOT_API_KEY not configured."
            )
        return f"No CRM record found for {name}."

    lines: list[str] = [f"CRM Profile: {contact.name}"]

    if contact.job_title or contact.company:
        role_parts = []
        if contact.job_title:
            role_parts.append(contact.job_title)
        if contact.company:
            role_parts.append(f"@ {contact.company}")
        lines.append("  Role: " + " ".join(role_parts))

    if contact.email:
        lines.append(f"  Email: {contact.email}")

    if contact.phone:
        lines.append(f"  Phone: {contact.phone}")

    if contact.lifecycle_stage:
        lines.append(f"  Lifecycle Stage: {contact.lifecycle_stage.replace('_', ' ').title()}")

    if contact.last_contacted:
        days_ago = (datetime.now(timezone.utc) - contact.last_contacted).days
        lines.append(f"  Last Contacted: {contact.last_contacted.strftime('%Y-%m-%d')} ({days_ago} days ago)")

    if contact.deals:
        lines.append(f"  Deals ({len(contact.deals)}):")
        for deal in contact.deals:
            deal_line = f"    - {deal.name}"
            if deal.stage:
                deal_line += f" [{deal.stage.replace('_', ' ').title()}]"
            if deal.amount is not None:
                deal_line += f" — ${deal.amount:,.0f}"
            if deal.close_date:
                deal_line += f" (closes {deal.close_date.strftime('%Y-%m-%d')})"
            lines.append(deal_line)

    if contact.notes:
        lines.append("  Notes:")
        for note in contact.notes[:3]:
            lines.append(f"    * {note}")

    return "\n".join(lines)
