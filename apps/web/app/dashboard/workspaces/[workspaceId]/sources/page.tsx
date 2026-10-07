import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import { sourceCatalog, uuid } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";
function values(items: string[] | null) {
  return items?.length
    ? items.join(", ")
    : "No values recorded / metadata unavailable";
}
export default async function Sources({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  if (!uuid(workspaceId)) notFound();
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/sources/`,
    sourceCatalog,
  );
  if (result.kind !== "ok") return <State kind={result.kind} />;
  const data = result.data;
  if (data.workspace.id !== workspaceId) return <State kind="unavailable" />;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>← Workspace</Link>
      <h1>Source configuration</h1>
      <p>{data.workspace.name}</p>
      <p className="notice">
        This shared catalog shows application configuration. It does not
        establish live availability, approved collection/storage/export rights,
        freshness or guaranteed coverage. Collection is unavailable.
      </p>
      <p>
        Saving a source code does not activate it. Enqueue requires current
        policy, entitlement and budget checks; export rights are assessed
        separately.
      </p>
      <div className="grid">
        {data.sources.map((source) => (
          <section className="card" key={source.code}>
            <h2>{source.code}</h2>
            <dl>
              <dt>Policy version</dt>
              <dd>{source.version}</dd>
              <dt>Configured switch</dt>
              <dd>
                {source.configured_enabled
                  ? "Enabled in configuration"
                  : "Disabled in configuration"}
              </dd>
              <dt>Free collection declaration</dt>
              <dd>
                {source.configured_free_collection
                  ? "Recorded as free; cost verification is separate"
                  : "Not recorded as free"}
              </dd>
              <dt>Configured countries</dt>
              <dd>{values(source.countries)}</dd>
              <dt>Configured categories</dt>
              <dd>{values(source.categories)}</dd>
              <dt>Configured business statuses</dt>
              <dd>{values(source.statuses)}</dd>
              <dt>Configured fields</dt>
              <dd>{values(source.fields)}</dd>
            </dl>
            {source.metadata_limited ? (
              <p>
                Capability metadata exceeds preview limits; values are not
                shown.
              </p>
            ) : null}
          </section>
        ))}
      </div>
      {data.sources.length === 0 ? (
        <p>
          No source policies are configured. You can save drafts; collection
          remains unavailable.
        </p>
      ) : null}
      {data.truncated ? (
        <p>
          Showing the first 100 policies by code. Additional entries are omitted
          from this preview.
        </p>
      ) : null}
    </>
  );
}
