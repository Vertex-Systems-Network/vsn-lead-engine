# SaaS UX and interaction contract

Design date: 2026-10-08 (Asia/Karachi)
Status: M3 implementation contract; no SaaS UI is deployed
Authority: MVP boundary PR #140, system/threat model PR #141, API/data contract PR #145, stack ADR #146

This contract turns the M3 UX acceptance items into screen behavior that can be implemented and tested. It supports a responsive web-first MVP for USA and Canada. It does not imply that any lead source, customer data use, price, legal basis or production service is approved.

## 1. Product shell and navigation

- Public pages: Home, capabilities, plans (clearly marked as planned concepts), privacy/data handling, sign-in and sign-up.
- Signed-in workspace navigation: Overview, Search, Jobs, Leads, Sources, Members, Usage, Settings.
- The active workspace name is always visible. Workspace switching requires an explicit selection and the server re-resolves membership on every request.
- Navigation items and actions are permission-aware, but hidden controls never substitute for server authorization.
- Do not show an empty billing path as functional. If plan concepts are shown, state that payments and subscriptions are not available.
- UI copy must distinguish implemented, test-only, planned, disabled and externally unverified capabilities.

## 2. Search setup and preview

A search wizard uses a stable four-step flow:

1. **Area** — choose one or more supported countries/regions and show any geographic limitations.
2. **Category and filters** — choose supported business categories, optional statuses and requested fields. Reject invalid or unsupported values inline.
3. **Sources and limits** — show each enabled source, supported capabilities, provenance/attribution, storage/export rights, freshness and known limitations. Disabled or unreviewed sources are visible only as unavailable with a concise reason.
4. **Review** — show normalized request scope, estimated accepted leads, job/lead/provider-call limits, estimated cost (or “unknown — dispatch unavailable”), and fields that may be absent. Require a final user action to create a job.

Behavior:
- Draft edits do not schedule or dispatch work.
- “Run search” is unavailable if no source is eligible, entitlement is inactive, cost is unknown for a paid action, or the requested scope exceeds limits.
- A source’s export prohibition does not prevent otherwise permitted search/storage. Export availability is separately explained and checked.
- Re-show the normalized request, hard caps and source policy version before each new job; never imply that estimates are guarantees.
- Form errors are tied to fields and summarized at the top. Preserve valid prior input after a validation error.

## 3. Schedule setup

- Scheduling is a distinct, opt-in action; saving a search does not create a recurring schedule.
- Require an IANA timezone and show the next three local occurrences with their UTC timestamps and offsets.
- Explain daylight-saving behavior beside the preview: nonexistent local times move to the next valid local instant that day; ambiguous times run once at the earlier UTC instant.
- Show the next run, pause state, current schedule revision and the owner/member permission required to edit it.
- Do not create a recurring schedule when the preview cannot be resolved or the entitlement/source policy disallows it.

## 4. Jobs and recovery

The jobs list and detail view use the domain states draft, queued, running, partial, completed, failed, paused, cancelled.

- Show requested scope, requested limit, actual accepted count, start/finish times, attempt count and source summary.
- Partial output is labeled “Partial”; requested counts are never represented as achieved counts.
- Detail shows redacted failure category, next safe action and whether retry/resume is available.
- Retry creates a visible new attempt under the same parent job context. Disable automatic retries for authorization, source-policy, entitlement or validation failures.
- Pause prevents future claims; cancellation is confirmed with a clear explanation of what stops and whether completed results remain accessible.
- A cancelled job has no resume action. Users can create a new job from the same search configuration.
- Provide accessible status text in addition to color and avoid rapid polling in the browser.

## 5. Leads, lineage and exports

- Table defaults to a bounded page size, opaque-cursor pagination and tenant-scoped filters.
- Each row exposes enough provenance to judge freshness: source name, observed date, field-level source where fields differ, freshness/confidence and attribution where required.
- Detail view separates business fields from provenance metadata and minimizes personal contact values until a user with permission opens the relevant detail.
- Export is a separate flow. Preview the selected fields, source restrictions, row cap, estimated usage/cost, expiry and available formats before requesting it.
- Omit fields that are not authorized by every relevant source policy; show exactly which fields were omitted and why.
- Download links are short-lived and shown only to an authorized member. Do not place signed URLs in logs or analytics.
- Viewer role has no export action. Server authorization still decides on every request.

## 6. Members, workspace and usage

- Members screen shows name/email, role, invitation state and last activity only where available and necessary.
- Owner/admin can invite or change roles. Prevent removing/demoting the last owner and explain how to transfer ownership.
- Invitation failures reveal safe recovery steps without exposing provider credentials.
- Workspace settings display timezone, locale, retention policy status and deletion/export request status. Unset legal or retention determinations are displayed as “not configured/review required”, never guessed.
- Usage screen shows server-derived counts and limits, current reservations, reset date only when defined, and an explanation of what consumes usage.
- Usage actions are blocked with a clear reason when the limit is reached; never offer a misleading upgrade checkout while billing is unavailable.

## 7. Accessibility and responsive behavior

Target WCAG 2.2 AA for the MVP:
- All flows work with keyboard only; focus order follows the visible sequence and focus is always visible.
- Every input has a persistent label; errors are programmatically associated and included in a summary that receives focus after failed submission.
- Tables have captions and header associations. Status and permission are expressed in text, not color alone.
- Content reflows at 320 CSS pixels without horizontal page scrolling except for explicitly scrollable data tables with a usable mobile alternative.
- Support zoom, high contrast, reduced motion and screen-reader announcements for asynchronous job changes.
- Use clear language, locale-aware dates/times and visible timezone labels; do not rely on ambiguous date formats.
- Touch targets meet WCAG 2.2 minimum target-size requirements or the spacing exception.

## 8. Empty, loading and failure states

Each primary screen defines explicit states:
- **Empty:** explain what can be created and the minimum requirements; do not fabricate records or live source examples.
- **Loading:** announce progress for screen readers and provide a stable skeleton without changing page geometry unnecessarily.
- **Unavailable source:** state disabled/unreviewed/rights-unknown with no run action.
- **Limit or cost block:** show the exact hard cap or why cost is unknown; no silent downgrade.
- **Network/server failure:** retain unsent form content where safe, identify whether the action may have been accepted and show the idempotency-backed job lookup path.
- **Permission loss/stale session:** stop mutations, return a safe sign-in or access-denied path and avoid revealing whether another workspace resource exists.

## 9. Analytics and privacy

- Product analytics, if later added, must not capture lead payloads, contact values, search text, member emails, credentials or signed URLs.
- Use aggregate event names and coarse status only after privacy review; analytics is disabled by default in the first implementation slice.
- Audit events are separate from product analytics and record only the actor, workspace, action, outcome and minimal resource reference needed for security review.
- Public marketing copy cannot claim coverage, accuracy, fresh data, legal compliance or results until evidence supports it.

## 10. Acceptance checks

A screen is ready for implementation review when:
1. Each state/action maps to the API contract and a role/entitlement rule.
2. All workspace-owned reads and mutations include actor/workspace context.
3. Empty, loading, error, denied, partial and success states are specified.
4. Search preview, schedule DST preview, job recovery and export preview are keyboard and screen-reader usable.
5. Test data is synthetic and cannot touch production Sheets/R2 or external providers.
6. No control implies payment, provider access or production readiness that is not available.

## Bounded implemented result-filter/selection refinement

The first result filter is country: All, US or Canada, using one native GET select with a persistent label. Counts distinguish shown, otherwise available but filtered, and currently unavailable rows. Filtered CSV review retains country and shows row checkboxes with authorized names/countries plus common field checkboxes, each in a labelled fieldset. At least one record and field are required server-side. The direct CSRF confirmation contains IDs only in the POST body and must remain within the signed filtered preview scope; stale/invalid selection returns safe review without an automatic replacement request. This is a single complete accepted batch of at most 25, without multi-batch pagination. Browser and accessibility certification remain pending.
