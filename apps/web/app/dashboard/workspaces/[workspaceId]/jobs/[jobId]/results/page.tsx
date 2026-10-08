import Link from "next/link";
import {
  resultFilters,
  resultFilterQuery,
} from "../../../../../../../lib/result-filter";
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
  searchParams,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const filters = resultFilters(await searchParams);
  if (filters === null) notFound();
  const query = resultFilterQuery(filters);
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/results/${query}`,
    savedResults,
  );
  if (result.kind !== "ok") return <State kind={result.kind} />;
  const data = result.data;
  if (
    data.workspace_id !== workspaceId ||
    data.job_id !== jobId ||
    data.country !== filters.country ||
    data.category_filter !== filters.category ||
    data.source_filter !== filters.source
  )
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
      <form method="get">
        <label htmlFor="result-country">Country</label>
        <select
          id="result-country"
          name="country"
          defaultValue={filters.country}
        >
          <option value="">All countries</option>
          <option value="US">United States</option>
          <option value="CA">Canada</option>
        </select>
        <label htmlFor="result-category">Saved category</label>
        <select
          id="result-category"
          name="category"
          defaultValue={filters.category}
        >
          <option value="">All saved categories</option>
          {data.category_options.map((label, index) => (
            <option key={label} value={String(index)}>
              {label}
            </option>
          ))}
        </select>
        <label htmlFor="result-source">Saved source</label>
        <select id="result-source" name="source" defaultValue={filters.source}>
          <option value="">All saved sources</option>
          {data.source_options.map((label, index) => (
            <option key={label} value={String(index)}>
              {label}
            </option>
          ))}
        </select>
        <button className="button" type="submit">
          Apply filters
        </button>
      </form>
      <p role="status">
        {data.results.length} shown; {data.filtered_count} available records
        excluded by filters.
      </p>
      <p>
        <Link
          prefetch={false}
          href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/results`}
        >
          Clear filters
        </Link>
      </p>
      {data.can_review_receipts ? (
        <p>
          <Link
            prefetch={false}
            href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/export-receipts`}
          >
            View export preparation receipts
          </Link>
        </p>
      ) : null}
      {data.can_review_export ? (
        <p>
          <Link
            prefetch={false}
            href={`/dashboard/workspaces/${workspaceId}/jobs/${jobId}/export${query}`}
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
            Choose All in each filter to clear them. A saved search or requested
            limit does not mean leads have been collected.
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
