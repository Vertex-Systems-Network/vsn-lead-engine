import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../../../lib/backend";
import {
  dailyOccurrenceHistory,
  uuid,
  workspace,
} from "../../../../../../../lib/contracts";
import { State } from "../../../../../../components/state";

export default async function DailyOccurrenceHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; planId: string }>;
  searchParams: Promise<{ before?: string }>;
}) {
  const [{ workspaceId, planId }, { before }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (
    !uuid(workspaceId) ||
    !uuid(planId) ||
    (before !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(before))
  )
    notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [history, identity] = await Promise.all([
    backend(
      `${base}daily-plans/${planId}/occurrences/${
        before ? `?before=${before}` : ""
      }`,
      dailyOccurrenceHistory,
    ),
    backend(base, workspace),
  ]);
  if (history.kind !== "ok") return <State kind={history.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    history.data.workspace_id !== workspaceId ||
    history.data.plan_id !== planId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans/${planId}`}>
        ← Saved plan details
      </Link>
      <p className="eyebrow">Recorded decisions only</p>
      <h1>Daily plan occurrence history</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        Read-only audit history, not a live scheduler. Each record describes a
        local-day decision that was already saved. Linked draft or queued jobs
        are not cancelled when a plan is paused. An empty history does not
        establish that recurring scheduling is running.
      </p>
      <p>{history.data.total} recorded local-day decisions for this plan.</p>
      {history.data.results.length ? (
        <div className="table-scroll">
          <table>
            <caption>
              Recorded daily occurrences (newest local dates first)
            </caption>
            <thead>
              <tr>
                <th scope="col">Local date</th>
                <th scope="col">Local time and timezone</th>
                <th scope="col">DST resolution</th>
                <th scope="col">Scheduled UTC instant</th>
                <th scope="col">Existing job status</th>
              </tr>
            </thead>
            <tbody>
              {history.data.results.map((entry) => (
                <tr key={entry.id}>
                  <th scope="row">{entry.local_date}</th>
                  <td>
                    {entry.local_time} · {entry.timezone}
                    <p>Revision {entry.schedule_revision}</p>
                  </td>
                  <td>{entry.resolution.replaceAll("_", " ")}</td>
                  <td>
                    {entry.scheduled_for
                      ? new Date(entry.scheduled_for).toISOString()
                      : "Skipped civil day — no job"}
                  </td>
                  <td>
                    {entry.job_id ? (
                      <Link
                        href={`/dashboard/workspaces/${workspaceId}/jobs/${entry.job_id}`}
                      >
                        {entry.job_status?.replaceAll("_", " ")} · Review job
                      </Link>
                    ) : (
                      "No job created"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No recorded daily occurrences on this page.</p>
      )}
      <nav className="pagination" aria-label="Occurrence history pages">
        {before ? (
          <Link
            href={`/dashboard/workspaces/${workspaceId}/daily-plans/${planId}/occurrences`}
          >
            First page
          </Link>
        ) : null}
        {history.data.next ? (
          <Link href={`?before=${history.data.next}`}>Earlier dates</Link>
        ) : null}
      </nav>
      <p className="muted">
        Saved decisions cannot prove that a lead provider was contacted, that
        leads were accepted, or that an operator authorized a recurring run.
        This screen performs no scheduling or mutation.
      </p>
    </>
  );
}
