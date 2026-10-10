import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import { memberAudits, uuid, workspace } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function MemberAuditPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ offset?: string }>;
}) {
  const [{ workspaceId }, { offset }] = await Promise.all([
    params,
    searchParams,
  ]);
  if (!uuid(workspaceId)) notFound();
  const current =
    typeof offset === "string" && /^(0|[1-9][0-9]{0,5})$/.test(offset)
      ? Number(offset)
      : 0;
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [report, identity] = await Promise.all([
    backend(`${base}member-audit/?offset=${current}`, memberAudits),
    backend(base, workspace),
  ]);
  if (report.kind !== "ok") return <State kind={report.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (identity.data.id !== workspaceId) return <State kind="unavailable" />;

  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/members`}>
        ← Workspace members
      </Link>
      <p className="eyebrow">Owner and administrator access review</p>
      <h1>Membership change audit history</h1>
      <p className="muted">
        Workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        Read-only history of recorded role changes and membership removals.
        Only current owners and admins may view this page. Events record UUIDs,
        not email addresses or customer lead details; this screen cannot
        invite, promote or remove anyone.
      </p>
      {report.data.results.length ? (
        <div className="table-scroll">
          <table>
            <caption>Recorded membership changes (UTC; newest first)</caption>
            <thead>
              <tr>
                <th scope="col">Timestamp (UTC)</th>
                <th scope="col">Action</th>
                <th scope="col">Actor UUID</th>
                <th scope="col">Target UUID</th>
                <th scope="col">Previous role</th>
                <th scope="col">New role</th>
              </tr>
            </thead>
            <tbody>
              {report.data.results.map((entry) => (
                <tr key={entry.id}>
                  <td>{entry.created_at}</td>
                  <td>{entry.action.replaceAll("_", " ")}</td>
                  <td>
                    <code>{entry.actor_user_id}</code>
                  </td>
                  <td>
                    <code>{entry.target_user_id}</code>
                  </td>
                  <td>{entry.previous_role}</td>
                  <td>{entry.new_role || "Removed"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No membership changes are recorded in this workspace.</p>
      )}
      <nav aria-label="Membership audit pages" className="pagination">
        {current > 0 && report.data.previous ? (
          <Link href={`?offset=${Math.max(0, current - 25)}`}>
            Previous 25 events
          </Link>
        ) : null}
        {report.data.next ? (
          <Link href={`?offset=${current + 25}`}>Next 25 events</Link>
        ) : null}
      </nav>
      <p className="muted">
        The history lists application-recorded membership mutations, not an
        external identity or compliance certification.
      </p>
    </>
  );
}
