import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import { members, uuid, workspace } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function MembersPage({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ page?: string }>;
}) {
  const [{ workspaceId }, { page }] = await Promise.all([params, searchParams]);
  if (!uuid(workspaceId)) notFound();

  const current =
    typeof page === "string" && /^[1-9][0-9]{0,5}$/.test(page)
      ? Number(page)
      : 1;
  const [result, identity] = await Promise.all([
    backend(
      `/api/v1/workspaces/${workspaceId}/members/?page=${current}`,
      members,
    ),
    backend(`/api/v1/workspaces/${workspaceId}/`, workspace),
  ]);
  if (result.kind !== "ok") return <State kind={result.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (identity.data.id !== workspaceId) return <State kind="unavailable" />;

  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>
        ← Workspace overview
      </Link>
      <p className="eyebrow">Workspace access</p>
      <h1>Workspace members</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="muted">
        Owners and administrators can review current workspace roles. This view
        is read-only: invitations, removals and role changes are not available
        from the Next dashboard.
      </p>
      {result.data.results.length > 0 ? (
        <div className="table-scroll">
          <table>
            <caption>Authorized workspace member roles</caption>
            <thead>
              <tr>
                <th scope="col">Member ID</th>
                <th scope="col">Role</th>
              </tr>
            </thead>
            <tbody>
              {result.data.results.map((member) => (
                <tr key={member.user_id}>
                  <th scope="row">
                    <code>{member.user_id}</code>
                  </th>
                  <td>{member.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No members appear on this page.</p>
      )}
      <nav aria-label="Member pages" className="pagination">
        {current > 1 ? (
          <Link href={`?page=${current - 1}`}>Previous page</Link>
        ) : null}
        {result.data.next ? (
          <Link href={`?page=${current + 1}`}>Next page</Link>
        ) : null}
      </nav>
      <p className="muted">
        Server permissions are checked on every request. A link or a visible
        member identifier never grants access to another workspace.
      </p>
    </>
  );
}
