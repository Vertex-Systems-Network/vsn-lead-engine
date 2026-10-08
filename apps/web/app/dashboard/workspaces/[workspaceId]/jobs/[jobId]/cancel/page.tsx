import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../../lib/backend";
import { cancelContext, job, uuid } from "../../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../../components/form-unavailable";
export default async function CancelDraft({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
  searchParams: Promise<{ notice?: string | string[] }>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const detail = `/dashboard/workspaces/${workspaceId}/jobs/${jobId}`;
  const { notice } = await searchParams;
  if (
    notice !== undefined &&
    !["invalid", "changed", "unavailable"].includes(notice as string)
  )
    notFound();
  if (notice) {
    const snapshot = await backend(
      `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/`,
      job,
    );
    if (snapshot.kind !== "ok") return <FormUnavailable kind={snapshot.kind} />;
    const current = snapshot.data;
    if (current.workspace_id !== workspaceId || current.id !== jobId)
      return <FormUnavailable kind="unavailable" />;
    return (
      <>
        <h1>Cancellation needs review</h1>
        <section className="card">
          <p className="notice" role="alert">
            {notice === "changed"
              ? "The job changed after confirmation was opened."
              : notice === "invalid"
                ? "The confirmation was invalid or expired."
                : "Cancellation is unavailable."}
          </p>
          <h2>{current.search.categories.join(", ")}</h2>
          <p>
            Current status: {current.status}. Revision: {current.revision}.
          </p>
          <p>
            This screen did not cancel the job. Review its details before
            opening a new confirmation. Started collection cannot be cancelled
            here.
          </p>
          <Link href={detail}>Review current job</Link>
        </section>
      </>
    );
  }
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/cancel-form/`,
    cancelContext,
  );
  if (result.kind !== "ok")
    return (
      <>
        <FormUnavailable kind={result.kind} />
        <p>
          <Link href={detail}>Review current job</Link>
        </p>
      </>
    );
  const data = result.data;
  if (data.workspace.id !== workspaceId || data.job.id !== jobId)
    return <FormUnavailable kind="unavailable" />;
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
