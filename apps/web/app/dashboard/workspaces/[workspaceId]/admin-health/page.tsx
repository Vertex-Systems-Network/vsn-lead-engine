import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import {
  operationalHealth,
  invitationHealthStates,
  operationalOutboxStates,
  preDispatchAttemptStates,
  jobStates,
  memberRoles,
  uuid,
  workspace,
} from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function OperationalHealthPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  if (!uuid(workspaceId)) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [snapshot, identity] = await Promise.all([
    backend(`${base}admin/health/`, operationalHealth),
    backend(base, workspace),
  ]);
  if (snapshot.kind !== "ok") return <State kind={snapshot.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    snapshot.data.workspace_id !== workspaceId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;

  const report = snapshot.data;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>
        ← Workspace overview
      </Link>
      <p className="eyebrow">Owner and administrator operations</p>
      <h1>Workspace operational health</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        Read-only, advisory snapshot of this workspace, not a consistent
        database transaction or evidence of a running worker, source rights,
        verified backup, delivery, billing or deployment. Unknown dispatches
        retain their usage reservations; this page never retries, refunds or
        cancels them.
      </p>
      <div className="grid">
        <section className="card" aria-labelledby="members-health">
          <h2 id="members-health">Membership roles</h2>
          <dl>
            {memberRoles.map((role) => (
              <div key={role}>
                <dt>{role}</dt>
                <dd>{report.member_roles[role]}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="card" aria-labelledby="invites-health">
          <h2 id="invites-health">Invitation states</h2>
          <dl>
            {invitationHealthStates.map((status) => (
              <div key={status}>
                <dt>{status}</dt>
                <dd>{report.invitations[status]}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="card" aria-labelledby="outstanding-health">
          <h2 id="outstanding-health">Outstanding operations</h2>
          <dl>
            <dt>Pending intents past expiry</dt>
            <dd>{report.expired_pending_outboxes}</dd>
            <dt>Expired intents eligible for safety recheck</dt>
            <dd>{report.eligible_expired_pending_intents}</dd>
            <dt>Pending intents with retained dispatch evidence</dt>
            <dd>{report.pending_possible_effect_intents}</dd>
            <dt>Unknown dispatch outcomes</dt>
            <dd>{report.unknown_dispatch_operations}</dd>
            <dt>Outstanding reserved usage intents</dt>
            <dd>{report.reserved_usage_intents}</dd>
          </dl>
        </section>
      </div>
      <div className="grid">
        <section className="card" aria-labelledby="job-health">
          <h2 id="job-health">Job states</h2>
          <dl>
            {jobStates.map((status) => (
              <div key={status}>
                <dt>{status}</dt>
                <dd>{report.jobs[status]}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="card" aria-labelledby="lease-health">
          <h2 id="lease-health">Pre-dispatch lease attempts</h2>
          <dl>
            {preDispatchAttemptStates.map((status) => (
              <div key={status}>
                <dt>{status}</dt>
                <dd>{report.pre_dispatch_attempts[status]}</dd>
              </div>
            ))}
            <dt>Leases past expiry, still recorded as leased</dt>
            <dd>{report.expired_leased_attempts}</dd>
          </dl>
          <p className="muted">
            Expired leases are diagnostic evidence only. No automatic retry,
            refund, release or dispatch is initiated by this screen.
          </p>
        </section>
        <section className="card" aria-labelledby="outbox-health">
          <h2 id="outbox-health">Outbox states</h2>
          <dl>
            {operationalOutboxStates.map((status) => (
              <div key={status}>
                <dt>{status}</dt>
                <dd>{report.outboxes[status]}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
      <p className="muted">
        Counts are scoped to current workspace authorization. Refresh the page
        for a new observation. No source data, lead contacts, tokens, invitation
        codes, member emails or job payloads are displayed.
      </p>
    </>
  );
}
