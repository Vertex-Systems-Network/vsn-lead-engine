import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../lib/backend";
import { dailyPlans, uuid, workspace } from "../../../../../lib/contracts";
import { State } from "../../../../components/state";

export default async function DailyPlansPage({
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
  const [plans, identity] = await Promise.all([
    backend(`${base}daily-plans/${after ? `?after=${after}` : ""}`, dailyPlans),
    backend(base, workspace),
  ]);
  if (plans.kind !== "ok") return <State kind={plans.kind} />;
  if (identity.kind !== "ok") return <State kind={identity.kind} />;
  if (
    plans.data.workspace_id !== workspaceId ||
    identity.data.id !== workspaceId
  )
    return <State kind="unavailable" />;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>
        ← Workspace overview
      </Link>
      <p className="eyebrow">Daily collection planning</p>
      <h1>Saved daily plans</h1>
      <p className="muted">
        Active workspace: <strong>{identity.data.name}</strong> ·{" "}
        {identity.data.timezone}
      </p>
      <p className="notice">
        These are stored plans, not running schedules. No automatic collection,
        recurring dispatch, provider requests or billing are activated from this
        screen. A plan&apos;s enabled flag reflects server state, not a control
        here.
      </p>
      <p>{plans.data.total} stored daily plans across all pages.</p>
      {plans.data.results.length ? (
        <div className="table-scroll">
          <table>
            <caption>Authorized workspace plans (up to 25 per page)</caption>
            <thead>
              <tr>
                <th scope="col">Plan ID</th>
                <th scope="col">Local time</th>
                <th scope="col">Timezone</th>
                <th scope="col">State</th>
                <th scope="col">Created (UTC)</th>
              </tr>
            </thead>
            <tbody>
              {plans.data.results.map((plan) => (
                <tr key={plan.id}>
                  <th scope="row">
                    <Link
                      href={`/dashboard/workspaces/${workspaceId}/daily-plans/${plan.id}`}
                    >
                      Review plan
                    </Link>
                    <p>
                      <code>{plan.id}</code>
                    </p>
                  </th>
                  <td>{plan.local_time}</td>
                  <td>{plan.timezone}</td>
                  <td>
                    {plan.enabled
                      ? "Enabled by separate operator action; not manageable here"
                      : "Disabled — no runs scheduled"}
                  </td>
                  <td>{new Date(plan.created_at).toISOString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>
          No saved daily plans on this page. Open a draft search to save a
          disabled daily plan.
        </p>
      )}
      <nav aria-label="Daily plan pages" className="pagination">
        {after ? (
          <Link href={`/dashboard/workspaces/${workspaceId}/daily-plans`}>
            First page
          </Link>
        ) : null}
        {plans.data.next ? (
          <Link href={`?after=${plans.data.next}`}>Next page</Link>
        ) : null}
      </nav>
      <p className="muted">
        Only current workspace members can read these records. Search criteria
        and lead/contact records are not exposed by this listing.
      </p>
    </>
  );
}
