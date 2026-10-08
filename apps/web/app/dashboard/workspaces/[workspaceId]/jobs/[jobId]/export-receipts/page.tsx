import Link from "next/link";
import { notFound } from "next/navigation";
import { backend } from "../../../../../../../lib/backend";
import {
  exportReceipts,
  receiptCursor,
  uuid,
} from "../../../../../../../lib/contracts";
import { State } from "../../../../../../components/state";

export default async function ReceiptHistory({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string; jobId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { workspaceId, jobId } = await params;
  if (!uuid(workspaceId) || !uuid(jobId)) notFound();
  const query = await searchParams;
  const after = query.after;
  if (
    Object.keys(query).some((k) => k !== "after") ||
    (after !== undefined && !receiptCursor(after))
  )
    notFound();
  const base = `/dashboard/workspaces/${workspaceId}/jobs/${jobId}`;
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/jobs/${jobId}/export-receipts/${query.after ? `?after=${encodeURIComponent(query.after as string)}` : ""}`,
    exportReceipts,
  );
  if (result.kind !== "ok")
    return (
      <>
        <State kind={result.kind} />
        <Link prefetch={false} href={`${base}/export-receipts`}>
          First receipt page
        </Link>
      </>
    );
  const data = result.data;
  if (data.workspace_id !== workspaceId || data.job_id !== jobId)
    return <State kind="unavailable" />;
  return (
    <>
      <Link prefetch={false} href={`${base}/results`}>
        ← Available results
      </Link>
      <h1>Export preparation receipts</h1>
      <p>
        {data.scope === "own"
          ? "Your preparations for this saved search."
          : "Preparations for this saved search across the workspace."}{" "}
        Newest first, at most 25 per page.
      </p>
      <p>
        Each receipt records one prepared CSV and one export unit. It does not
        confirm a successful download. CSV files are not retained. A new export
        preview is a new request and may use another unit; current permissions
        and retention still apply.
      </p>
      {data.receipts.length === 0 ? (
        <section className="card">
          <h2>No preparation receipts</h2>
          <p>
            No settled export preparations are available in your current scope.
          </p>
        </section>
      ) : null}
      {data.receipts.map((r) => (
        <section className="card" key={r.id}>
          <h2>Prepared {new Date(r.prepared_at).toISOString()} (UTC)</h2>
          <dl>
            <dt>Receipt</dt>
            <dd>{r.id}</dd>
            <dt>Records in prepared file</dt>
            <dd>{r.record_count}</dd>
            <dt>Export units used</dt>
            <dd>{r.export_units}</dd>
            <dt>Recorded source deadline (UTC)</dt>
            <dd>{new Date(r.retention_deadline).toISOString()}</dd>
            <dt>Recorded deadline</dt>
            <dd>
              {r.deadline_passed ? "Passed" : "Not yet passed"}. This is not a
              download or permission guarantee.
            </dd>
          </dl>
        </section>
      ))}
      <nav aria-label="Receipt pages">
        <Link prefetch={false} href={`${base}/export-receipts`}>
          First receipt page
        </Link>
        {data.next_cursor ? (
          <Link
            prefetch={false}
            href={`?after=${encodeURIComponent(data.next_cursor)}`}
          >
            Older receipts
          </Link>
        ) : null}
      </nav>
    </>
  );
}
