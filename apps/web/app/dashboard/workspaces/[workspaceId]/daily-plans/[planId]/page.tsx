import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../lib/backend";
import {
  dailyPlanDetail,
  uuid,
  workspace,
} from "../../../../../../lib/contracts";
import { State } from "../../../../../components/state";

export default async function DailyPlanDetailPage({
  params,
}: {
  params: Promise<{ workspaceId: string; planId: string }>;
}) {
  const { workspaceId, planId } = await params;
  if (!uuid(workspaceId) || !uuid(planId)) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [plan, identity] = await Promise.all([
    backend(`${base}daily-plans/${planId}/`, dailyPlanDetail),
    backend(base, workspace),
  ]);
  if (plan.kind !== "ok") return <State kind={plan.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    plan.data.workspace_id !== workspaceId ||
    plan.data.id !== planId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;

  const item = plan.data;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans`}>
        ← Saved daily plans
      </Link>
      <p className="eyebrow">Review saved schedule configuration</p>
      <h1>Daily plan details</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        This is a read-only snapshot of your plan, not a running cron job.
        Saving or viewing a plan does not activate a schedule, collect leads,
        contact a source or charge a customer. Source permissions and coverage
        must be verified separately before any execution.
      </p>
      <p>
        <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans/${planId}/readiness`}>
          Review internal source readiness (admins)
        </Link>
      </p>
      <section className="card">
        <h2>Saved local time</h2>
        <dl>
          <dt>Plan ID</dt>
          <dd>
            <code>{item.id}</code>
          </dd>
          <dt>Local time</dt>
          <dd>{item.local_time}</dd>
          <dt>Timezone</dt>
          <dd>{item.timezone}</dd>
          <dt>Current plan state</dt>
          <dd>
            {item.enabled
              ? "Enabled by a separate operator action — no controls here"
              : "Disabled — no runs scheduled"}
          </dd>
          <dt>Revision</dt>
          <dd>{item.revision}</dd>
          <dt>Created (UTC)</dt>
          <dd>{new Date(item.created_at).toISOString()}</dd>
        </dl>
      </section>
      <section className="card">
        <h2>Saved lead search preferences</h2>
        <dl>
          <dt>Countries</dt>
          <dd>{item.search.countries.join(", ")}</dd>
          <dt>Business categories</dt>
          <dd>{item.search.categories.join(", ")}</dd>
          <dt>Requested business statuses</dt>
          <dd>{item.search.statuses.join(", ") || "No preference"}</dd>
          <dt>Required result fields</dt>
          <dd>{item.search.required_fields.join(", ")}</dd>
          <dt>Requested source codes</dt>
          <dd>{item.search.source_codes.join(", ") || "None selected"}</dd>
          <dt>Requested maximum results per draft</dt>
          <dd>{item.search.result_limit}</dd>
        </dl>
      </section>
      <p>
        <Link
          href={`/dashboard/workspaces/${workspaceId}/daily-plans/${planId}/occurrences`}
        >
          View recorded daily occurrences and existing jobs
        </Link>
      </p>
      {item.enabled ? (
        <p>
          <a
            href={backendLink(
              `/workspaces/${workspaceId}/daily-plans/${planId}/pause/`,
            )}
          >
            Pause future daily occurrences (owner/admin confirmation)
          </a>
        </p>
      ) : null}
      <p className="muted">
        These are saved requests, not verified provider availability, lead
        counts, source rights or a guarantee of results. No activation or edit
        operation is offered.
      </p>
    </>
  );
}
