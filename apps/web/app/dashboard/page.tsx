import Link from "next/link";
import { backend } from "../../lib/backend";
import { workspaces } from "../../lib/contracts";
import { State } from "../components/state";
export default async function Dashboard({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page } = await searchParams;
  const current =
    typeof page === "string" && /^[1-9][0-9]{0,5}$/.test(page)
      ? Number(page)
      : 1;
  const result = await backend(
    `/api/v1/workspaces/?page=${current}`,
    workspaces,
  );
  if (result.kind !== "ok") return <State kind={result.kind} />;
  return (
    <>
      <p className="eyebrow">Your operations</p>
      <h1>Workspaces</h1>
      <p className="muted">
        Open a workspace to review saved searches and usage.
      </p>
      <section className="grid" aria-label="Workspaces">
        {result.data.results.map((w) => (
          <article className="card" key={w.id}>
            <h2>{w.name}</h2>
            <p className="muted">{w.timezone}</p>
            <Link className="button" href={`/dashboard/workspaces/${w.id}`}>
              Open workspace
            </Link>
          </article>
        ))}
      </section>
      {result.data.results.length === 0 ? (
        <p>No workspaces are assigned to this account.</p>
      ) : null}
      <nav aria-label="Workspace pages" className="pagination">
        {current > 1 ? (
          <Link href={`?page=${current - 1}`}>Previous</Link>
        ) : null}
        {result.data.next ? (
          <Link href={`?page=${current + 1}`}>Next page</Link>
        ) : null}
      </nav>
    </>
  );
}
