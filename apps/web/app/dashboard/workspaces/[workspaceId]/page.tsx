import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../lib/backend";
import { jobs, usage, uuid, counterNames } from "../../../../lib/contracts";
import { State } from "../../../components/state";
export default async function Workspace({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ after?: string }>;
}) {
  const [{ workspaceId }, { after }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (!uuid(workspaceId) || (after !== undefined && !uuid(after))) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [history, counters] = await Promise.all([
    backend(`${base}jobs/${after ? `?after=${after}` : ""}`, jobs),
    backend(`${base}usage/`, usage),
  ]);
  if (history.kind !== "ok") return <State kind={history.kind} />;
  if (history.data.results.some((j) => j.workspace_id !== workspaceId))
    return <State kind="unavailable" />;
  return (
    <>
      <Link href="/dashboard">← Workspaces</Link>
      <h1>Workspace overview</h1>
      <div className="actions">
        <Link
          className="button"
          prefetch={false}
          href={`/dashboard/workspaces/${workspaceId}/search/new`}
        >
          Create draft search
        </Link>
        <Link href={`/dashboard/workspaces/${workspaceId}/sources`}>
          Source configuration
        </Link>
      </div>
      <p className="notice">
        Drafts save your search preferences. Collection and exports are not yet
        available.
      </p>
      <h2>Usage</h2>
      {counters.kind === "ok" && counters.data.workspace_id === workspaceId ? (
        <>
          <p className="muted">
            {counters.data.period ? (
              <>
                Internal accounting window:{" "}
                {new Date(counters.data.period.starts_at).toISOString()} to{" "}
                {new Date(counters.data.period.ends_at).toISOString()}. Rollover
                waits for unresolved reservations; billing is unavailable.
              </>
            ) : (
              <>
                Cumulative development counters. No billing period or reset is
                configured.
              </>
            )}
          </p>
          <div className="table-scroll">
            <table>
              <caption>Settled and reserved usage</caption>
              <thead>
                <tr>
                  <th scope="col">Counter</th>
                  <th scope="col">Settled</th>
                  <th scope="col">Reserved</th>
                  <th scope="col">Limit</th>
                </tr>
              </thead>
              <tbody>
                {counterNames.map((key) => (
                  <tr key={key}>
                    <th scope="row">{key.replaceAll("_", " ")}</th>
                    <td>{counters.data.counters[key].settled}</td>
                    <td>{counters.data.counters[key].reserved}</td>
                    <td>{counters.data.counters[key].limit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p>Usage is currently unavailable.</p>
      )}
      <h2>Saved searches</h2>
      <p className="muted">
        Ordered by stable job identity; up to 25 records per page.
      </p>
      <div className="grid">
        {history.data.results.map((j) => (
          <article className="card" key={j.id}>
            <span className="badge">{j.status}</span>
            <h3>{j.search.categories.join(", ")}</h3>
            <p>{j.search.countries.join(" · ")}</p>
            <p className="muted">{j.result_count} recorded results</p>
            <Link href={`/dashboard/workspaces/${workspaceId}/jobs/${j.id}`}>
              View search
            </Link>
          </article>
        ))}
      </div>
      {history.data.results.length === 0 ? <p>No saved searches yet.</p> : null}
      <nav aria-label="Search pages" className="pagination">
        {after ? (
          <Link href={`/dashboard/workspaces/${workspaceId}`}>First page</Link>
        ) : null}
        {history.data.next ? (
          <Link href={`?after=${history.data.next}`}>Next page</Link>
        ) : null}
      </nav>
    </>
  );
}
