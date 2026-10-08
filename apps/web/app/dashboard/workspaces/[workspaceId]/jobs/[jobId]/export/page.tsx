import Link from "next/link";
import {
  resultFilters,
  resultFilterQuery,
} from "../../../../../../../lib/result-filter";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../../lib/backend";
import { exportContext, uuid } from "../../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../../components/form-unavailable";

export default async function ExportResults({
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
  const back = `/dashboard/workspaces/${workspaceId}/jobs/${jobId}/results${query}`;
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/export-form/${query}`,
    exportContext,
  );
  if (result.kind !== "ok")
    return (
      <>
        <FormUnavailable kind={result.kind} />
        <p>
          <Link href={back}>Review current results</Link>
        </p>
      </>
    );
  const data = result.data;
  if (
    data.workspace_id !== workspaceId ||
    data.job_id !== jobId ||
    data.country !== filters.country ||
    data.category_filter !== filters.category ||
    data.source_filter !== filters.source
  )
    return <FormUnavailable kind="unavailable" />;
  return (
    <>
      <Link prefetch={false} href={back}>
        ← Available results
      </Link>
      <h1>Review CSV export</h1>
      <section className="card">
        <h2>{data.record_count} currently available records</h2>
        <p>
          Choose which currently available records to export from this initial
          batch. {data.filtered_count} available records are excluded by the
          filters. {data.withheld_count} recorded results are unavailable and
          excluded.
        </p>
        <p>
          Country: {data.country || "All"}; saved category:{" "}
          {data.category_filter
            ? data.category_options[Number(data.category_filter)]
            : "All"}
          ; saved source:{" "}
          {data.source_filter
            ? data.source_options[Number(data.source_filter)]
            : "All"}
          .
        </p>
        <p>
          Preparing this CSV uses one export unit. Repeating the same
          confirmation and selection does not charge another unit. Opening a new
          preview creates a new export request.
        </p>
        <p>
          Confirmation expires at {new Date(data.expires_at).toISOString()}{" "}
          (UTC), or sooner if permissions change. Source, policy, observation,
          retention and attribution are included with your selected fields.
        </p>
        <h2>Source attribution</h2>
        <ul>
          {data.sources.map((s) => (
            <li key={s.code}>
              {s.code}: {s.attribution}
            </li>
          ))}
        </ul>
        {data.omitted_fields.length > 0 ? (
          <p>
            Unavailable fields: {data.omitted_fields.join(", ")}. Current source
            rights or stored field availability exclude them from this batch.
          </p>
        ) : null}
        <form
          method="post"
          action={backendLink(
            `/workspaces/${workspaceId}/jobs/${jobId}/export/`,
          )}
        >
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={data.csrf_token}
          />
          <input type="hidden" name="confirmation" value={data.confirmation} />
          <fieldset>
            <legend>Choose records to include (at least one)</legend>
            {data.records.map((record) => (
              <label key={record.id}>
                <input
                  type="checkbox"
                  name="result_ids"
                  value={record.id}
                  defaultChecked
                />
                {record.business_name} ({record.country})
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>Choose fields to include (at least one)</legend>
            {data.fields.map((field) => (
              <label key={field}>
                <input
                  type="checkbox"
                  name="fields"
                  value={field}
                  defaultChecked
                />
                {field.replaceAll("_", " ")}
              </label>
            ))}
          </fieldset>
          <p>
            Formula-like spreadsheet values, including +phone values, receive a
            leading apostrophe for safety. Keep downloaded copies within the
            source retention terms.
          </p>
          <button className="button" type="submit">
            Confirm and download CSV
          </button>
        </form>
      </section>
    </>
  );
}
