import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../lib/backend";
import {
  jobs,
  usage,
  workspace,
  uuid,
  counterNames,
  jobStates,
  jobState,
  jobStatusSummary,
} from "../../../../lib/contracts";
import { State } from "../../../components/state";
export default async function Workspace({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ after?: string; status?: string }>;
}) {
  const [{ workspaceId }, { after, status }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (!uuid(workspaceId) || (after !== undefined && !uuid(after))) notFound();
  if (status !== undefined && status !== "" && !jobState(status)) notFound();
  const selected = status || undefined;
  const query = new URLSearchParams();
  if (selected) query.set("status", selected);
  if (after) query.set("after", after);
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [history, counters, identity, summary] = await Promise.all([
    backend(`${base}jobs/${query.size ? `?${query}` : ""}`, jobs),
    backend(`${base}usage/`, usage),
    backend(base, workspace),
    backend(`${base}job-summary/`, jobStatusSummary),
  ]);
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (identity.data.id !== workspaceId) return <State kind="unavailable" />;
  if (history.kind !== "ok") return <State kind={history.kind} />;
  if (summary.kind !== "ok") return <State kind={summary.kind} />;
  if (summary.data.workspace_id !== workspaceId)
    return <State kind="unavailable" />;
  if (
    history.data.results.some(
      (j) =>
        j.workspace_id !== workspaceId || (selected && j.status !== selected),
    )
  )
    return <State kind="unavailable" />;
  return (
    <>
      <Link href="/dashboard">← Workspaces</Link>
      <h1>Workspace overview</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
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
        <Link href={`/dashboard/workspaces/${workspaceId}/members`}>
          Workspace members (admins)
        </Link>
        <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans`}>
          Saved daily plans
        </Link>
        <a href={backendLink(`/workspaces/${workspaceId}/schedule-preview/`)}>
          Daily time preview
        </a>
      </div>
      <p className="notice">
        Drafts save search preferences without collecting leads. Submitted jobs
        require an eligible source, a current entitlement and a running worker.
        Production SaaS service is not yet deployed.
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
      <section aria-labelledby="job-status-summary-title">
        <h2 id="job-status-summary-title">Job status summary</h2>
        <p className="muted">
          {summary.data.total} saved searches across all pages. These counts are
          job states, not accepted leads or a guaranteed collection volume.
        </p>
        <div className="grid">
          {jobStates.map((state) => (
            <article className="card" key={state}>
              <h3>{state.replaceAll("_", " ")}</h3>
              <p>
                <strong>{summary.data.statuses[state]}</strong> jobs
              </p>
              <Link href={`?status=${state}`}>View {state} jobs</Link>
            </article>
          ))}
        </div>
      </section>
      <h2>Saved searches</h2>
      <form
        className="actions"
        method="get"
        action={`/dashboard/workspaces/${workspaceId}`}
      >
        <label htmlFor="job-status">Job status</label>
        <select id="job-status" name="status" defaultValue={selected ?? ""}>
          <option value="">All jobs</option>
          {jobStates.map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
        <button type="submit">Apply filter</button>
      </form>
      <p className="muted">
        Filters apply to saved job state. Requested business status remains part
        of each search.
      </p>
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
      {history.data.results.length === 0 ? (
        <p>
          {after
            ? "No saved searches on this page."
            : selected
              ? "No saved searches match this status."
              : "No saved searches yet."}
        </p>
      ) : null}
      <nav aria-label="Search pages" className="pagination">
        {after ? (
          <Link
            href={`/dashboard/workspaces/${workspaceId}${selected ? `?status=${selected}` : ""}`}
          >
            First page
          </Link>
        ) : null}
        {history.data.next ? (
          <Link
            href={`?${selected ? `status=${selected}&` : ""}after=${history.data.next}`}
          >
            Next page
          </Link>
        ) : null}
      </nav>
    </>
  );
}
