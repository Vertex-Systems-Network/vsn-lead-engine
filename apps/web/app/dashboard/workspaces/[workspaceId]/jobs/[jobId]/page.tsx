import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../lib/backend";
import { job, uuid } from "../../../../../../lib/contracts";
import { AutoRefresh } from "../../../../../components/auto-refresh";
import { State } from "../../../../../components/state";
export default async function Detail({
  params,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/`,
    job,
  );
  if (result.kind !== "ok") return <State kind={result.kind} />;
  const j = result.data;
  if (j.workspace_id !== workspaceId || j.id !== jobId)
    return <State kind="unavailable" />;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>← Workspace</Link>
      <h1>Saved search</h1>
      <Link
        prefetch={false}
        href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/results`}
      >
        View available results
      </Link>
      <section className="card">
        <span className="badge">{j.status}</span>
        <h2>{j.search.categories.join(", ")}</h2>
        <dl>
          <dt>Countries</dt>
          <dd>{j.search.countries.join(", ")}</dd>
          <dt>Recorded results</dt>
          <dd>{j.result_count}</dd>
          <dt>Revision</dt>
          <dd>{j.revision}</dd>
          <dt>Created (UTC)</dt>
          <dd>{new Date(j.created_at).toISOString()}</dd>
        </dl>
        {j.status === "draft" ? (
          <p>
            <Link
              prefetch={false}
              className="button"
              href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/submit`}
            >
              Submit job
            </Link>
          </p>
        ) : null}
        {j.status === "draft" ? (
          <p>
            <a
              href={backendLink(
                `/workspaces/${workspaceId}/jobs/${jobId}/daily-plan/`,
              )}
            >
              Save a disabled daily plan
            </a>
          </p>
        ) : null}
        {["queued", "running"].includes(j.status) ? (
          <p className="notice">
            {j.status === "queued"
              ? "Queued for collection. This page updates automatically."
              : "Collecting leads. This page updates automatically."}
            <AutoRefresh />
          </p>
        ) : null}
        {j.status === "failed" && j.result_count === 0 ? (
          <p className="notice">
            No new leads were found for this search; unused allowance was
            released.
          </p>
        ) : null}
        {["draft", "queued"].includes(j.status) ? (
          <Link
            prefetch={false}
            href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/cancel`}
          >
            Review cancellation
          </Link>
        ) : null}
      </section>
    </>
  );
}
