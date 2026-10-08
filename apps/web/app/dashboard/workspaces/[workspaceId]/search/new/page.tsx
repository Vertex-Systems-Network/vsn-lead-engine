import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../../../../lib/backend";
import {
  draftContext,
  draftFeedback,
  uuid,
} from "../../../../../../lib/contracts";
import { FormUnavailable } from "../../../../../components/form-unavailable";
export default async function NewDraft({
  params,
  searchParams,
}: {
  params: Promise<{ workspaceId: string }>;
  searchParams: Promise<{ feedback?: string | string[] }>;
}) {
  const { workspaceId } = await params;
  if (!uuid(workspaceId)) notFound();
  const { feedback } = await searchParams;
  if (feedback !== undefined && !uuid(feedback)) notFound();
  const result = feedback
    ? await backend(
        `/api/v1/workspaces/${workspaceId}/draft-feedback/${feedback}/`,
        draftFeedback,
      )
    : await backend(
        `/api/v1/workspaces/${workspaceId}/draft-form/`,
        draftContext,
      );
  if (result.kind !== "ok")
    return (
      <>
        <FormUnavailable kind={result.kind} />
        {feedback ? (
          <p>
            This saved form may have expired or become unavailable.{" "}
            <Link
              href={`/dashboard/workspaces/${workspaceId}/search/new`}
              prefetch={false}
            >
              Open a new draft form
            </Link>{" "}
            or{" "}
            <Link href={`/dashboard/workspaces/${workspaceId}`}>
              return to your workspace
            </Link>
            .
          </p>
        ) : null}
      </>
    );
  const data = result.data;
  if (data.workspace.id !== workspaceId)
    return <FormUnavailable kind="unavailable" />;
  const values = data.kind === "draft-feedback" ? data.values : undefined;
  const errors = data.kind === "draft-feedback" ? data.errors : {};
  const error = (field: string) =>
    errors[field]?.length ? (
      <p id={`${field}-error`} className="notice">
        {errors[field].join(" ")}
      </p>
    ) : null;
  return (
    <>
      <Link href={`/dashboard/workspaces/${workspaceId}`}>← Workspace</Link>
      <h1>Create draft search</h1>
      <p>{data.workspace.name}</p>
      <p className="notice">
        Save your search preferences. A draft does not run collection or reserve
        usage.
      </p>
      {data.kind === "draft-feedback" ? (
        <section className="notice" aria-labelledby="error-heading">
          <h2 id="error-heading">
            {data.status === 409
              ? "Draft submission conflict"
              : "Check your search"}
          </h2>
          <ul>
            {Object.entries(errors).flatMap(([field, messages]) =>
              messages.map((message, i) => (
                <li key={`${field}-${i}`}>
                  {field === "__all__" ? (
                    message
                  ) : (
                    <a href={`#${field}`}>{message}</a>
                  )}
                </li>
              )),
            )}
          </ul>
          <Link
            href={`/dashboard/workspaces/${workspaceId}/search/new`}
            prefetch={false}
          >
            Open a new draft form
          </Link>
        </section>
      ) : null}
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
        <fieldset
          id="countries"
          aria-invalid={!!errors.countries}
          tabIndex={-1}
          aria-describedby={errors.countries ? "countries-error" : undefined}
        >
          <legend>Countries</legend>
          <label>
            <input
              type="checkbox"
              name="countries"
              value="US"
              defaultChecked={values ? values.countries.includes("US") : true}
            />{" "}
            United States
          </label>
          <label>
            <input
              type="checkbox"
              name="countries"
              value="CA"
              defaultChecked={values?.countries.includes("CA")}
            />{" "}
            Canada
          </label>
        </fieldset>
        {error("countries")}
        <label htmlFor="categories">Categories</label>
        <textarea
          id="categories"
          name="categories"
          rows={3}
          maxLength={1600}
          required
          defaultValue={values?.categories}
          aria-invalid={!!errors.categories}
          aria-describedby={`categories-help${errors.categories ? " categories-error" : ""}`}
        />
        <p id="categories-help" className="muted">
          One category per line, up to 12. Source coverage is unverified.
        </p>
        {error("categories")}
        <fieldset
          id="statuses"
          aria-invalid={!!errors.statuses}
          tabIndex={-1}
          aria-describedby={errors.statuses ? "statuses-error" : undefined}
        >
          <legend>Business status (optional)</legend>
          {[
            ["active", "Active"],
            ["closed", "Closed"],
            ["opening_soon", "Opening soon"],
          ].map(([value, label]) => (
            <label key={value}>
              <input
                type="checkbox"
                name="statuses"
                value={value}
                defaultChecked={values?.statuses.includes(value)}
              />{" "}
              {label}
            </label>
          ))}
        </fieldset>
        {error("statuses")}
        <fieldset
          id="required_fields"
          aria-invalid={!!errors.required_fields}
          tabIndex={-1}
          aria-describedby={
            errors.required_fields ? "required_fields-error" : undefined
          }
        >
          <legend>Requested fields</legend>
          <label>
            <input type="checkbox" defaultChecked disabled /> Phone (always
            required)
          </label>
          {["name", "website", "address"].map((value) => (
            <label key={value}>
              <input
                type="checkbox"
                name="required_fields"
                value={value}
                defaultChecked={values?.required_fields.includes(value)}
              />{" "}
              {value}
            </label>
          ))}
        </fieldset>
        {error("required_fields")}
        <label htmlFor="source_codes">Source codes (optional)</label>
        <textarea
          id="source_codes"
          name="source_codes"
          rows={2}
          maxLength={900}
          defaultValue={values?.source_codes}
          aria-invalid={!!errors.source_codes}
          aria-describedby={`sources-help${errors.source_codes ? " source_codes-error" : ""}`}
        />
        <p id="sources-help" className="muted">
          One code per line, up to 12. Saving does not activate sources.
        </p>
        {error("source_codes")}
        <label htmlFor="result_limit">Requested result limit</label>
        <input
          id="result_limit"
          name="result_limit"
          type="number"
          min={1}
          max={1000}
          defaultValue={values?.result_limit ?? 100}
          aria-invalid={!!errors.result_limit}
          aria-describedby={
            errors.result_limit ? "result_limit-error" : undefined
          }
          required
        />
        {error("result_limit")}
        <button className="button" type="submit">
          Save draft
        </button>
      </form>
    </>
  );
}
