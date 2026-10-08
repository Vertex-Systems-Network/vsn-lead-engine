import Link from "next/link";
import { Fragment } from "react";
import { notFound } from "next/navigation";
import { backend } from "../../../../../../../lib/backend";
import {
  savedResults,
  uuid,
  resultFieldNames,
} from "../../../../../../../lib/contracts";
import { State } from "../../../../../../components/state";

export default async function Results({
  params,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/results/`,
    savedResults,
  );
  if (result.kind !== "ok") return <State kind={result.kind} />;
  const data = result.data;
  if (data.workspace_id !== workspaceId || data.job_id !== jobId)
    return <State kind="unavailable" />;
  return (
    <>
      <Link
        prefetch={false}
        href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}`}
      >
        ← Saved search
      </Link>
      <h1>Available results</h1>
      {data.can_review_export ? (
        <p>
          <Link
            prefetch={false}
            href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/export`}
          >
            Review CSV export
          </Link>
        </p>
      ) : null}
      <p>
        Records shown pass current source rights and retention checks. Recorded
        job totals may include results that are no longer available. This
        initial batch contains at most 25 records.
      </p>
      {data.withheld_count > 0 ? (
        <p role="status">
          {data.withheld_count} recorded results are currently unavailable.
        </p>
      ) : null}
      {data.results.length === 0 ? (
        <section className="card">
          <h2>No available results</h2>
          <p>
            A saved search or requested limit does not mean leads have been
            collected.
          </p>
        </section>
      ) : null}
      {data.results.map((row) => (
        <section className="card" key={row.id}>
          <h2>{row.fields.business_name}</h2>
          <p>
            {row.country} · {row.category}
          </p>
          <dl>
            {resultFieldNames
              .filter((key) => row.fields[key])
              .map((key) => (
                <Fragment key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{row.fields[key]}</dd>
                </Fragment>
              ))}
            <dt>Source / policy</dt>
            <dd>
              {row.source_code} / {row.policy_version}
            </dd>
            <dt>Observed (UTC)</dt>
            <dd>{new Date(row.observed_at).toISOString()}</dd>
            <dt>Retention deadline (UTC)</dt>
            <dd>{new Date(row.delete_at).toISOString()}</dd>
            <dt>Retention version</dt>
            <dd>{row.retention_version}</dd>
            <dt>Fields from this source</dt>
            <dd>{row.provenance_fields.join(", ")}</dd>
          </dl>
        </section>
      ))}
    </>
  );
}
