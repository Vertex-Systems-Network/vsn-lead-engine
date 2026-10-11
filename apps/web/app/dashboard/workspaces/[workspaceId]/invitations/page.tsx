import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../lib/backend";
import {
  pendingInvitations,
  uuid,
  workspace,
} from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function PendingInvitationsPage({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  if (!uuid(workspaceId)) notFound();
  const base = `/api/v1/workspaces/${workspaceId}/`;
  const [pending, identity] = await Promise.all([
    backend(`${base}invitations/pending/`, pendingInvitations),
    backend(base, workspace),
  ]);
  if (pending.kind !== "ok") return <State kind={pending.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    identity.data.id !== workspaceId ||
    pending.data.workspace_id !== workspaceId
  )
    return <State kind="unavailable" />;

  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}/members`}>
        ← Workspace members
      </Link>
      <p className="eyebrow">Owner and administrator access review</p>
      <h1>Pending workspace invitations</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        Review up to ten pending invitations for existing accounts. No email,
        SMS or automatic delivery occurs. Codes appear only once at issuance and
        are never available on this page. Inviting or revoking requires a
        separate CSRF-protected Django confirmation.
      </p>
      <p>
        <a href={backendLink(`/workspaces/${workspaceId}/invitations/new/`)}>
          Issue an invitation to an existing user →
        </a>
      </p>
      {pending.data.results.length > 0 ? (
        <div className="table-scroll">
          <table>
            <caption>Pending invitations in this workspace</caption>
            <thead>
              <tr>
                <th scope="col">Target username</th>
                <th scope="col">Requested role</th>
                <th scope="col">Expires (UTC)</th>
                <th scope="col">Review action</th>
              </tr>
            </thead>
            <tbody>
              {pending.data.results.map((invitation) => (
                <tr key={invitation.id}>
                  <th scope="row">{invitation.target_username}</th>
                  <td>{invitation.role}</td>
                  <td>{invitation.expires_at}</td>
                  <td>
                    {invitation.can_revoke ? (
                      <a
                        href={backendLink(
                          `/workspaces/${workspaceId}/invitations/${invitation.id}/revoke/`,
                        )}
                      >
                        Review revocation
                      </a>
                    ) : (
                      "Owner only"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No pending invitations remain in this workspace.</p>
      )}
      <p className="muted">
        Listing and visible links never grant permission. The Django server
        rechecks current role, invitation validity and a signed confirmation
        before any revocation.
      </p>
    </>
  );
}
