# SaaS Prototype Test Runbook

**Status:** Prepared for future moderated research; no participants have completed a session.  
**Research snapshot:** 2026-10-05 PKT  
**Parent workbench:** `docs/ai/LEAD-SAAS-USER-MARKET-RESEARCH.md`  
**Scope:** Manual, low-fidelity usability/discovery sessions using fictional mock screens and data only. This is not a live product or provider test.

## Objective

Observe how people with recent first-hand business-list workflows attempt three jobs:

1. Configure a local business/place search and decide when its results are usable.
2. Explain what they do when they need named contacts for those businesses.
3. Configure a recurring run and specify the limits/controls they would require.

The session tests task comprehension and unmet requirements. It does not prove market size, demand, willingness to pay, data rights, source quality, or product-market fit.

## Session setup

- Recruit only people who pass the parent workbench screener. Prefer 8–12 external participants across two or more plausible segments; include at least some people who do not buy prospecting tools or are satisfied with their current process.
- Use participant IDs such as `P01`; keep scheduling contact details in a separate location and delete them after scheduling/follow-up unless the person asks for contact.
- Do not ask for customer lists, lead records, personal data, credentials, screenshots of private systems, or confidential client workflows.
- Show the same prototype copy, fictional records, and task order logic to all participants.
- Use only mock screens; no API, real search, export, source lookup, job schedule, email, payment, or data persistence.
- Do not record audio/video in this runbook. Ask separately for consent to take anonymized notes before starting.
- If consent to notes is declined, thank the person and do not collect research notes.
- Target 30 minutes. If the session is shorter, record uncompleted topics as unknown rather than fill gaps from assumptions.

## Moderator script and run order

### 1. Welcome and consent (2 minutes)

Read:

> Thanks for speaking with me. I’m researching how people build and use business lead lists. This is not a sales call, and criticism is helpful. I’ll ask about a recent real workflow, then show a research mock with fictional data. It will not search, save, export, schedule, or contact anyone. Please do not share confidential client records or personal information. You can skip any question or stop at any time. May I take anonymized notes?

Record yes/no and proceed only after a clear yes. Do not infer consent from attendance.

### 2. Recent workflow (8 minutes)

Ask in this order; use only neutral follow-ups (“What happened next?”, “How did you decide?”, “Can you describe the last example without sharing records?”):

- Tell me about the last time you personally built, purchased, or requested a business/contact list.
- What triggered the request, and when was it?
- Walk me through the steps and tools from request to delivery.
- What did you accept or reject in the result? Which fields were required?
- What took the most time or caused a failure? What did you do then?
- How often has this happened in the last 90 days?
- Who selected the tools or approved spending?
- What happens to the list after delivery?

Capture behavior and exact anonymized quotes separately from interpretation. Do not introduce VSN features during this section.

### 3. Task T1 — Local business discovery (6 minutes)

Read exactly:

> You have been asked to prepare a list of independent auto repair businesses in one city for a client. Use this research mock the way you would normally prepare the list. Stop when you believe it is ready.

Observe silently. Do not point to controls or explain terms unless the participant is blocked. If they ask about actual results, say: “These are fictional mock rows. This screen does not search a real source.” After they stop, ask:

- What would make this output unusable in your real work?
- What source, freshness, or quality evidence would you need before handing it over?
- What would you do next in your current process?

Record task completion as observed, not as a pass/fail judgment.

### 4. Task T2 — Contact discovery branch (5 minutes)

From the mock results, show the optional contact-discovery branch and read:

> Your client now needs the person responsible for purchasing at these businesses. Show what you would do next in your real process.

Do not invent contacts or imply an available connector. Ask:

- Would you continue here, switch tools, ask a teammate, or do something else?
- What information would you need to trust a contact record?
- Would contact discovery belong in the same job or a separate one? Why?

Capture whether their actual recent workflow joins these jobs, and what evidence would change their view.

### 5. Task T3 — Recurring job and controls (5 minutes)

Show the recurring-job mock and read:

> Your client wants this list refreshed every Monday. Configure what you would need before you would be comfortable leaving it unattended. It is a simulation only.

Observe schedule/timezone, cap, pause/cancel, notifications, approval expectations, and handling of partial/failure cases. Ask:

- What would you need to see before saving this schedule?
- Who should approve paid usage or a changed source?
- What should happen if a run is partial, fails, finds no results, or reaches its limit?
- How would you want to stop or change it?

### 6. Neutral concept debrief (3 minutes)

Ask:

- What is confusing or missing in the flow?
- What would you remove?
- What parts are already handled well by your current approach?
- What would stop you from trying a tool like this?
- Is there an important workflow we did not discuss?

Do not ask “Would you buy this?” as a substitute for observed behavior. If the participant volunteers future intent, label it as opinion, not demonstrated demand.

### 7. Close (1 minute)

Thank the participant. Ask if a follow-up clarification would be welcome; do not add them to a mailing list. Record only whether follow-up was invited.

## Observation rubric

For each task, record the following without assigning a pre-set pass score:

| Measure | Record |
|---|---|
| Task outcome | Completed / stopped / participant chose another workflow / not attempted |
| Time | Approximate start-to-stop duration; note interruptions |
| Help | None / neutral clarification / moderator guidance; quote the guidance if given |
| Path | Screen/choice sequence in participant's words |
| Friction | Misread label, missing control, wrong turn, hesitation, workaround |
| Required data | Fields explicitly named as required, optional, or unacceptable |
| Trust conditions | Requested source/provenance, freshness, validation, attribution, deletion |
| Cost/controls | Estimate, cap, plan, approval, notification or stop conditions named |
| Evidence class | Observed behavior / participant-reported recent fact / opinion / researcher interpretation |
| Counterexample | Current process works, no repeat need, no budget authority, or required data unavailable |
| Quote | Short anonymized exact phrase if it changes a decision |
| Confidence | High/medium/low with reason; never use confidence as a substitute for evidence |

A “completed” task means the person reaches a point they themselves call ready without the moderator completing actions for them. It does not mean the workflow meets a business requirement.

## Session capture sheet

Copy one record per participant; use `unknown` where not learned.

```text
Participant ID:
Date / interviewer:
Screener segment and recent-work fit:
Consent to anonymized notes: yes/no
Current job / trigger / recency:
Frequency and actual steps:
Tools and handoffs:
Required fields and rejection rules:
Quality, freshness, provenance expectations:
Time/cost/failure described:
Budget or tool decision role:
T1 outcome/path/friction:
T2 outcome/path/friction:
T3 outcome/path/friction:
Current workaround and what works well:
Direct anonymized quote:
Counterexample or contradiction:
Observed facts:
Participant-reported facts:
Opinions/future intent:
Researcher interpretation:
Open questions / follow-up:
```

## Cross-session synthesis

After each session, normalize observations into a separate row per claim, tagged with participant ID and evidence class. Keep direct observations, participant-reported facts, opinions, and interpretations in separate columns. Summarize counts as “n of interviewed participants”; do not present a convenience sample as representative of a market.

Before recommending a segment or MVP:

1. Compare recent workflow, recurrence, user/buyer, required fields, failure cost and workaround by segment.
2. Preserve conflicting evidence and include at least one disconfirming case where available.
3. Separate prototype usability defects from evidence that the underlying job is not important.
4. Revisit source rights, coverage, freshness and cost as independent gates; interview enthusiasm cannot clear them.
5. Propose success thresholds only after sessions and explain the rationale before running a larger usability test.
6. Leave segment, price, source, payment route, stack, and MVP decisions open until the owner accepts/rejects them through the project decision process.

## Research log and decision memo template

```text
Decision question:
Date and evidence window:
Participants/segments observed (n only):
Repeated recent behaviors:
Requirements repeated across participants:
Contradictions and counterexamples:
Prototype friction unrelated to the core job:
Unvalidated statements/opinions:
Source/legal/cost gates still open:
Recommendation: go to another test / hold and narrow / stop or reframe
Evidence and rationale:
Decision owner / approval status:
```

No participant has been recruited, interviewed, or task-tested through this runbook at the snapshot date. Keep the research work unit in progress until the sessions and evidence review are complete, or explicitly record a human recruitment blocker without claiming validation.
