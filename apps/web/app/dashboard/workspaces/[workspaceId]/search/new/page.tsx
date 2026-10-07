import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../lib/backend";
import { draftContext, uuid } from "../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../components/form-unavailable";
export default async function NewDraft({
  params,
}: {
  params: Promise<{ workspaceId: string }>;
}) {
  const { workspaceId } = await params;
  if (!uuid(workspaceId)) notFound();
  const result = await backend(
    `/api/v1/workspaces/${workspaceId}/draft-form/`,
    draftContext,
  );
  if (result.kind !== "ok") return <FormUnavailable kind={result.kind} />;
  const data = result.data;
  if (data.workspace.id !== workspaceId)
    return <FormUnavailable kind="unavailable" />;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>← Workspace</Link>
      <h1>Create draft search</h1>
      <p>{data.workspace.name}</p>
      <p className="notice">
        Save your search preferences. A draft does not run collection or reserve
        usage.
      </p>
      <form
        className="card search-form"
        method="post"
        action={backendLink(`/workspaces/${workspaceId}/search/new/`)}
      >
        <input
          type="hidden"
          name="csrfmiddlewaretoken"
          value={data.csrf_token}
        />
        <input type="hidden" name="draft_token" value={data.draft_token} />
        <fieldset>
          <legend>Countries</legend>
          <label>
            <input type="checkbox" name="countries" value="US" defaultChecked />{" "}
            United States
          </label>
          <label>
            <input type="checkbox" name="countries" value="CA" /> Canada
          </label>
        </fieldset>
        <label htmlFor="categories">Categories</label>
        <textarea
          id="categories"
          name="categories"
          rows={3}
          maxLength={1600}
          required
          aria-describedby="categories-help"
        />
        <p id="categories-help" className="muted">
          One category per line, up to 12. Source coverage is unverified.
        </p>
        <fieldset>
          <legend>Business status (optional)</legend>
          {[
            ["active", "Active"],
            ["closed", "Closed"],
            ["opening_soon", "Opening soon"],
          ].map(([value, label]) => (
            <label key={value}>
              <input type="checkbox" name="statuses" value={value} /> {label}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>Requested fields</legend>
          <label>
            <input type="checkbox" defaultChecked disabled /> Phone (always
            required)
          </label>
          {["name", "website", "address"].map((value) => (
            <label key={value}>
              <input type="checkbox" name="required_fields" value={value} />{" "}
              {value}
            </label>
          ))}
        </fieldset>
        <label htmlFor="sources">Source codes (optional)</label>
        <textarea
          id="sources"
          name="source_codes"
          rows={2}
          maxLength={900}
          aria-describedby="sources-help"
        />
        <p id="sources-help" className="muted">
          One code per line, up to 12. Saving does not activate sources.
        </p>
        <label htmlFor="limit">Requested result limit</label>
        <input
          id="limit"
          name="result_limit"
          type="number"
          min={1}
          max={1000}
          defaultValue={100}
          required
        />
        <p className="muted">
          Submission is checked by the account service. Any validation errors
          open its review form.
        </p>
        <button className="button" type="submit">
          Save draft
        </button>
      </form>
    </>
  );
}
