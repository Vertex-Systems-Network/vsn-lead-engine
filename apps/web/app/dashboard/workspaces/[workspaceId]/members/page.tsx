import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../lib/backend";
import { members, uuid, workspace } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function MembersPage({
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
  const [result, identity] = await Promise.all([
    backend(
      `/api/v1/workspaces/${workspaceId}/members/?offset=${current}`,
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
        lists verified member roles. Role changes require a separate signed and
        CSRF-protected confirmation. Removals require a separate explicit
        warning and confirmation. Existing-account invitations use a separate private one-time code and explicit acceptance; no messages are sent automatically.
      </p>
      <p>
        <a href={backendLink(`/workspaces/${workspaceId}/invitations/new/`)}>
          Invite an existing user with a private one-time code →
        </a>
      </p>
      {result.data.results.length > 0 ? (
        <div className="table-scroll">
          <table>
            <caption>Authorized workspace member roles</caption>
            <thead>
              <tr>
                <th scope="col">Member ID</th>
                <th scope="col">Role</th>
                <th scope="col">Admin action</th>
              </tr>
            </thead>
            <tbody>
              {result.data.results.map((member) => (
                <tr key={member.user_id}>
                  <th scope="row">
                    <code>{member.user_id}</code>
                  </th>
                  <td>{member.role}</td>
                  <td>
                    <a
                      href={backendLink(
                        `/workspaces/${workspaceId}/members/${member.user_id}/role/`,
                      )}
                    >
                      Review role change
                    </a>
                    {" · "}
                    <a
                      href={backendLink(
                        `/workspaces/${workspaceId}/members/${member.user_id}/remove/`,
                      )}
                    >
                      Review removal
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No members appear on this page.</p>
      )}
      <nav aria-label="Member pages" className="pagination">
        {current > 0 ? (
          <Link href={`?offset=${Math.max(0, current - 25)}`}>
            Previous page
          </Link>
        ) : null}
        {result.data.next ? (
          <Link href={`?offset=${current + 25}`}>Next page</Link>
        ) : null}
      </nav>
      <p>
        <Link href={`/dashboard/workspaces/${workspaceId}/member-audit`}>
          Review member role change history →
        </Link>
      </p>
      <p className="muted">
        Server permissions are checked on every request. A link or a visible
        member identifier never grants access to another workspace.
      </p>
    </>
  );
}
