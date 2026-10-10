import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../../lib/backend";
import { job, submitContext, uuid } from "../../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../../components/form-unavailable";
export default async function SubmitJob({
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
    !["invalid", "changed", "unavailable", "limits"].includes(notice as string)
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
        <h1>Submission needs review</h1>
        <section className="card">
          <p className="notice" role="alert">
            {notice === "limits"
              ? "This workspace cannot run this search right now: its plan is inactive, its limits are used up, or no enabled source covers this search."
              : notice === "changed"
                ? "The job changed after confirmation was opened."
                : notice === "invalid"
                  ? "The confirmation was invalid or expired."
                  : "Submission is unavailable."}
          </p>
          <h2>{current.search.categories.join(", ")}</h2>
          <p>
            Current status: {current.status}. Revision: {current.revision}.
          </p>
          <p>This screen did not submit the job.</p>
          <Link href={detail}>Review current job</Link>
        </section>
      </>
    );
  }
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/submit-form/`,
    submitContext,
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
      <h1>Submit job</h1>
      <section className="card">
        <h2>{data.job.search.categories.join(", ")}</h2>
        <p>
          Countries: {data.job.search.countries.join(", ")}. Revision:{" "}
          {data.job.revision}.
        </p>
        <p>
          Submitting reserves this search&apos;s allowance and queues it for
          collection. One job returns at most 25 new leads; leads already
          delivered to this workspace are not repeated, and unused allowance is
          released if nothing new is found.
        </p>
        <form
          method="post"
          action={backendLink(
            `/workspaces/${workspaceId}/jobs/${jobId}/submit/`,
          )}
        >
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={data.csrf_token}
          />
          <input type="hidden" name="confirmation" value={data.confirmation} />
          <button className="button" type="submit">
            Confirm and submit
          </button>
        </form>
        <p>
          <Link href={detail}>Keep as draft</Link>
        </p>
      </section>
    </>
  );
}
