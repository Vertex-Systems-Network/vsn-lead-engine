import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../../../lib/backend";
import {
  planReadiness,
  uuid,
  workspace,
} from "../../../../../../../lib/contracts";
import { State } from "../../../../../../components/state";

export default async function DailyPlanReadinessPage({
  params,
}: {
  params: Promise<{ workspaceId: string; planId: string }>;
}) {
  const { workspaceId, planId } = await params;
  if (!uuid(workspaceId) || !uuid(planId)) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [report, identity] = await Promise.all([
    backend(`${base}daily-plans/${planId}/readiness/`, planReadiness),
    backend(base, workspace),
  ]);
  if (report.kind !== "ok") return <State kind={report.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    report.data.workspace_id !== workspaceId ||
    report.data.plan_id !== planId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;
  const passed = report.data.status === "internal_catalog_match_only";
  const affordable = report.data.catch_up_budget_snapshot.affordable_due_job_candidates;
  const deferred = report.data.catch_up_budget_snapshot.deferred_due_job_candidates;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans/${planId}`}>
        ← Daily plan details
      </Link>
      <p className="eyebrow">Owner/admin internal policy preview</p>
      <h1>Daily plan source readiness review</h1>
      <p className="muted">
        Workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        <strong>
          {passed ? "Internal catalog checks match" : "Internal checks blocked"}
        </strong>
        . This is a read-only internal snapshot, not permission to collect
        leads, enable a schedule, contact providers or charge anyone. Operator
        records cannot independently prove legal source rights, usable quota,
        production credentials or provider availability.
      </p>
      <p>
        Plan currently{" "}
        {report.data.stored_enabled ? "enabled in stored state" : "disabled"}.{" "}
        Internal source policies checked: {report.data.checked_source_count}.
      </p>
      <div className="table-scroll">
        <table>
          <caption>Stored configuration and internal catalog checks</caption>
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {report.data.checks.map((item) => (
              <tr key={item.name}>
                <th scope="row">{item.name.replaceAll("_", " ")}</th>
                <td>
                  {item.status === "pass" ? "Internal check passed" : "Blocked"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2>Single-job usage headroom (read-only estimate)</h2>
      <p className="notice">
        {report.data.budget_snapshot.status.replaceAll("_", " ")}. The figures
        apply to one hypothetical submitted job, not seven catch-up dates or
        future recurring runs. No budget is reserved by this screen; other
        concurrent jobs may consume the available allowance before submission.
      </p>
      {report.data.budget_snapshot.counters.length ? (
        <div className="table-scroll">
          <table>
            <caption>Internal quota and pending reservation snapshot</caption>
            <thead>
              <tr>
                <th scope="col">Resource</th>
                <th scope="col">Requested</th>
                <th scope="col">Settled</th>
                <th scope="col">Pending</th>
                <th scope="col">Limit</th>
                <th scope="col">Estimated headroom</th>
              </tr>
            </thead>
            <tbody>
              {report.data.budget_snapshot.counters.map((item) => (
                <tr key={item.name}>
                  <th scope="row">{item.name.replaceAll("_", " ")}</th>
                  <td>{item.requested}</td>
                  <td>{item.settled}</td>
                  <td>{item.reserved}</td>
                  <td>{item.limit}</td>
                  <td>{item.headroom}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Capacity not available for this configuration.</p>
      )}
      <h2>Seven-local-day catch-up allowance (read-only estimate)</h2>
      <p className="notice">
        Status:{" "}
        {report.data.catch_up_budget_snapshot.status.replaceAll("_", " ")}.
        Potential due-job drafts:{" "}
        {report.data.catch_up_budget_snapshot.due_job_candidates} within at most
        seven local calendar dates. Skipped civil dates:{" "}
        {report.data.catch_up_budget_snapshot.skipped_day_candidates}. This is a
        hypothetical combined allowance estimate, not a job reservation or a
        running scheduler. Disabled plans have no runnable due candidates, and
        already-recorded days are excluded.
      </p>
      {affordable === null ? (
        <p className="muted">
          Affordable catch-up estimate unavailable: an active entitlement and
          valid accounting window are required. No capacity is authorized.
        </p>
      ) : (
        <p className="notice">
          Current simultaneous allowance covers at most{" "}
          <strong>{affordable}</strong> hypothetical due jobs;{" "}
          <strong>{deferred}</strong> would exceed this snapshot. This is not an
          execution order, reservation or permission to start them.
        </p>
      )}
      {report.data.catch_up_budget_snapshot.counters.length ? (
        <div className="table-scroll">
          <table>
            <caption>Aggregate hypothetical backlog quota comparison</caption>
            <thead>
              <tr>
                <th scope="col">Resource</th>
                <th scope="col">All due jobs requested</th>
                <th scope="col">Current estimated headroom</th>
              </tr>
            </thead>
            <tbody>
              {report.data.catch_up_budget_snapshot.counters.map((row) => (
                <tr key={row.name}>
                  <th scope="row">{row.name.replaceAll("_", " ")}</th>
                  <td>{row.requested}</td>
                  <td>{row.headroom}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Catch-up allowance unavailable or plan disabled.</p>
      )}
      <h2>Not verified — required before any execution</h2>
      <ul>
        {report.data.unverified_execution_gates.map((gate) => (
          <li key={gate}>{gate.replaceAll("_", " ")}</li>
        ))}
      </ul>
      <p className="muted">
        Catalog consistency is not source consent, commercial clearance,
        entitlement capacity or scheduler release certification. This page
        performs no writes and has no activation controls.
      </p>
    </>
  );
}
