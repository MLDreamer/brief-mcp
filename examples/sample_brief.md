# Sample Meeting Brief Output

This is an example of the formatted brief card that `get_meeting_brief` and
`brief_all_today` produce. This represents a realistic output for a partnership
review call.

---

## Example conversation

**User prompt to Claude:**
> "Brief me for my 2pm meeting today."

**Claude calls:** `get_upcoming_meetings()` → `get_meeting_brief(meeting_title="Q4 Partnership Review")`

**Claude's response:**

---

Here's your brief for the 2pm call:

```
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
     Bio     : Seasoned engineering leader with 15 years in distributed
               systems and developer tooling. Joined PartnerCo in 2022
               after leading infrastructure at DataStream Inc.
     LinkedIn: VP of Engineering at PartnerCo. Led the migration to
               Kubernetes-native architecture. Previously Staff Engineer
               at Google, Amazon, and DataStream Inc.
     Recent  :
       - Bob Patel promoted to VP of Engineering at PartnerCo (Sept 2026)
       - "The infrastructure challenges no one talks about" — Bob Patel on Dev.to
       - PartnerCo Engineering Blog: new latency benchmarks published
     Co News :
       - PartnerCo raises $50M Series B to accelerate AI platform
       - PartnerCo announces APAC expansion, opens Singapore office

  >> Carol Wu
     Role    : Director of Product @ PartnerCo
     Bio     : Product leader with 10 years in enterprise SaaS. Joined
               PartnerCo from Google in early 2026 to lead the developer
               platform product suite.
     LinkedIn: Director of Product at PartnerCo, ex-Google PM for
               Firebase. Focused on making developer tools delightful
               at enterprise scale.
     Recent  :
       - Carol Wu joins PartnerCo from Google as Director of Product
       - Carol Wu keynote at ProductCon SF 2026: "AI-native product design"
     Co News :
       - PartnerCo launches new AI platform (Oct 2026)

------------------------------------------------------------
  SUGGESTED TALKING POINTS
------------------------------------------------------------
  1. Ask Bob about his priorities as VP of Engineering — particularly the
     new Kubernetes platform and how the Acme integration fits in.
  2. Reference PartnerCo's Series B — congratulate them and ask how the
     funding changes their roadmap for the integration.
  3. Ask Carol about her vision for the developer experience coming from
     her Firebase background — alignment opportunity.
  4. Review Q3 milestones together before discussing Q4 plan.
  5. Confirm owner and timeline for the API authentication work before
     the call ends.

------------------------------------------------------------
  WATCH-OUTS / SENSITIVITIES
------------------------------------------------------------
  ! PartnerCo just raised a Series B — they may reprioritize or want to
    renegotiate commercial terms. Come prepared to discuss contract value.
  ! Carol is new (joined from Google in 2026) — she may not have full
    context on the existing integration history. Don't assume she's read
    all the prior docs.

------------------------------------------------------------
  CONTEXT NOTES
------------------------------------------------------------
  * Meeting is 60 minutes — leave last 10 min for next-steps and owner
    assignments.
  * PartnerCo's Singapore office opens Q1 2027 — opportunity to discuss
    APAC deployment of the integration.

  Generated: 2026-10-13 09:14
============================================================
```

---

## Example: brief_all_today output header

When you call `brief_all_today()`, it prefixes the individual briefs with:

```
DAILY BRIEFING — Tuesday, October 13 2026
3 meeting(s) today
############################################################

[brief for Meeting 1]

[brief for Meeting 2]

[brief for Meeting 3]
```

---

## What makes a good brief

The brief card aims to surface:

1. **Who** — role, seniority, and background in under 30 seconds of reading
2. **What's new** — recent news about them and their company (last 30-90 days)
3. **What to say** — concrete talking points tailored to the meeting context
4. **What to watch** — sensitivities, power dynamics, time constraints

All research is generated automatically from public web sources and takes
roughly 5-15 seconds per attendee (faster on cache hits).
