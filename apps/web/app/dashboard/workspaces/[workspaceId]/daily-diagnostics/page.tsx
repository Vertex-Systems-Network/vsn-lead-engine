import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import { dueDiagnostics, uuid, workspace } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function DueDiagnosticsPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ after?: string }>;
}) {
  const [{ workspaceId }, { after }] = await Promise.all([params, searchParams]);
  if (!uuid(workspaceId) || (after !== undefined && !uuid(after))) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [report, identity] = await Promise.all([
    backend(
      `${base}daily-diagnostics/${after ? `?after=${after}` : ""}`,
      dueDiagnostics,
    ),
    backend(base, workspace),
  ]);
  if (report.kind !== "ok") return <State kind={report.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    report.data.workspace_id !== workspaceId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;

  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans`}>
        ← Saved daily plans
      </Link>
      <p className="eyebrow">Owner/admin diagnostic preview</p>
      <h1>Daily schedule readiness review</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        Advisory snapshot only — not a live scheduler. A due candidate does not
        grant permission to run any collection, create a job, contact a
        provider, reserve usage or activate billing. All execution gates must
        be rechecked separately. This screen has no activation controls.
      </p>
      <p>
        Inspected {report.data.inspected} plans on this page, out of{" "}
        {report.data.total_plans} stored. Snapshot time:{" "}
        {new Date(report.data.as_of_utc).toISOString()}.
      </p>
      <div className="table-scroll">
        <table>
          <caption>Redacted read-only daily plan diagnostics</caption>
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Stored state</th>
              <th scope="col">Diagnostic status</th>
              <th scope="col">Unmaterialized local-date candidates</th>
            </tr>
          </thead>
          <tbody>
            {report.data.plans.map((plan) => (
              <tr key={plan.id}>
                <th scope="row">
                  <Link
                    href={`/dashboard/workspaces/${workspaceId}/daily-plans/${plan.id}`}
                  >
                    Review plan
                  </Link>
                  <p><code>{plan.id}</code></p>
                </th>
                <td>{plan.enabled ? "Enabled (external action)" : "Disabled"}</td>
                <td>{plan.status.replaceAll("_", " ")}</td>
                <td>
                  {plan.due_local_dates.length
                    ? plan.due_local_dates
                        .map((day) => `${day.local_date} (${day.resolution})`)
                        .join(", ")
                    : "None"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {report.data.plans.length === 0 ? (
        <p>No plans appear on this page.</p>
      ) : null}
      <nav className="pagination" aria-label="Diagnostic pages">
        {after ? (
          <Link
            href={`/dashboard/workspaces/${workspaceId}/daily-diagnostics`}
          >
            First page
          </Link>
        ) : null}
        {report.data.next ? (
          <Link href={`?after=${report.data.next}`}>Next page</Link>
        ) : null}
      </nav>
      <p className="muted">
        Remaining execution gates: {report.data.requires_execution_gates.join(", ")}.
        This report does not verify provider availability, source rights,
        credentials, spend authorization, scheduled execution or launch.
      </p>
    </>
  );
}
