import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../../lib/backend";
import { cancelContext, uuid } from "../../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../../components/form-unavailable";
export default async function CancelDraft({
  params,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/cancel-form/`,
    cancelContext,
  );
  if (result.kind !== "ok") return <FormUnavailable kind={result.kind} />;
  const data = result.data;
  if (data.workspace.id !== workspaceId || data.job.id !== jobId)
    return <FormUnavailable kind="unavailable" />;
  const detail = `/dashboard/workspaces/${workspaceId}/jobs/${jobId}`;
  return (
    <>
      <Link href={detail}>← Saved search</Link>
      <h1>Review cancellation</h1>
      <section className="card">
        <h2>{data.job.search.categories.join(", ")}</h2>
        <p>
          Current status: {data.job.status}. Revision: {data.job.revision}.
        </p>
        <p>
          Cancel this pending job? Collection that has already started cannot be
          cancelled here.
        </p>
        <form
          method="post"
          action={backendLink(
            `/workspaces/${workspaceId}/jobs/${jobId}/cancel/`,
          )}
        >
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={data.csrf_token}
          />
          <input type="hidden" name="confirmation" value={data.confirmation} />
          <button className="button" type="submit">
            Confirm cancellation
          </button>
        </form>
        <p>
          <Link href={detail}>Keep job</Link>
        </p>
      </section>
    </>
  );
}
