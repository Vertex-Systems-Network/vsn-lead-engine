import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../../lib/backend";
import { job, uuid } from "../../../../../../lib/contracts";
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
