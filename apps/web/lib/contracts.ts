export const uuid = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const object = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const count = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
export type Workspace = { id: string; name: string; timezone: string };
export function workspace(v: unknown): v is Workspace {
  return (
    object(v) &&
    uuid(v.id) &&
    typeof v.name === "string" &&
    typeof v.timezone === "string"
  );
}
export type Workspaces = {
  results: Workspace[];
  count: number;
  next: string | null;
};
export function workspaces(v: unknown): v is Workspaces {
  return (
    object(v) &&
    count(v.count) &&
    (v.next === null || typeof v.next === "string") &&
    Array.isArray(v.results) &&
    v.results.length <= 25 &&
    v.results.every(workspace)
  );
}
export const memberRoles = ["owner", "admin", "member", "viewer"] as const;
export type Member = {
  user_id: string;
  role: (typeof memberRoles)[number];
};
export type Members = {
  count: number;
  next: string | null;
  results: Member[];
};
export function members(v: unknown): v is Members {
  return (
    object(v) &&
    count(v.count) &&
    (v.next === null || typeof v.next === "string") &&
    Array.isArray(v.results) &&
    v.results.length <= 25 &&
    v.results.every(
      (m) =>
        object(m) &&
        uuid(m.user_id) &&
        memberRoles.includes(m.role as Member["role"]),
    ) &&
    new Set(v.results.map((m: Member) => m.user_id)).size === v.results.length
  );
}

export type Job = {
  id: string;
  workspace_id: string;
  status: string;
  result_count: number;
  revision: number;
  search: { countries: string[]; categories: string[] };
  created_at: string;
};
export type Jobs = { results: Job[]; next: string | null };
export function job(v: unknown): v is Job {
  return (
    object(v) &&
    uuid(v.id) &&
    uuid(v.workspace_id) &&
    typeof v.status === "string" &&
    count(v.result_count) &&
    count(v.revision) &&
    typeof v.created_at === "string" &&
    Number.isFinite(Date.parse(v.created_at)) &&
    object(v.search) &&
    Array.isArray(v.search.countries) &&
    v.search.countries.every((s) => typeof s === "string") &&
    Array.isArray(v.search.categories) &&
    v.search.categories.every((s) => typeof s === "string")
  );
}
export function jobs(v: unknown): v is Jobs {
  return (
    object(v) &&
    Array.isArray(v.results) &&
    v.results.length <= 25 &&
    v.results.every(job) &&
    (v.next === null || uuid(v.next))
  );
}
export const counterNames = [
  "leads",
  "jobs",
  "provider_calls",
  "exports",
] as const;
export type Usage = {
  workspace_id: string;
  entitlement_active: boolean;
  accounting: "cumulative_development" | "period_development";
  period: null | { id: string; starts_at: string; ends_at: string };
  counters: Record<
    (typeof counterNames)[number],
    { settled: number; reserved: number; limit: number }
  >;
};
export function usage(v: unknown): v is Usage {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    typeof v.entitlement_active !== "boolean" ||
    !["cumulative_development", "period_development"].includes(
      String(v.accounting),
    ) ||
    !object(v.counters)
  )
    return false;
  if (v.accounting === "period_development") {
    if (
      !object(v.period) ||
      !uuid(v.period.id) ||
      typeof v.period.starts_at !== "string" ||
      typeof v.period.ends_at !== "string" ||
      !Number.isFinite(Date.parse(v.period.starts_at)) ||
      !Number.isFinite(Date.parse(v.period.ends_at)) ||
      Date.parse(v.period.ends_at) <= Date.parse(v.period.starts_at)
    )
      return false;
  } else if (v.period !== null) return false;
  const counters = v.counters;
  return counterNames.every((key) => {
    const c = counters[key];
    return object(c) && count(c.settled) && count(c.reserved) && count(c.limit);
  });
}

export type DraftContext = {
  kind: "draft";
  workspace: { id: string; name: string };
  csrf_token: string;
  draft_token: string;
};
export type CancelContext = {
  kind: "cancel";
  workspace: { id: string; name: string };
  csrf_token: string;
  confirmation: string;
  job: Job;
};
export type SubmitContext = {
  kind: "submit";
  workspace: { id: string; name: string };
  csrf_token: string;
  confirmation: string;
  job: Job;
};
function formBase(v: unknown): v is Record<string, unknown> {
  return (
    object(v) &&
    object(v.workspace) &&
    uuid(v.workspace.id) &&
    typeof v.workspace.name === "string" &&
    v.workspace.name.length <= 120 &&
    typeof v.csrf_token === "string" &&
    /^[A-Za-z0-9]{64}$/.test(v.csrf_token)
  );
}
function signedToken(v: unknown): v is string {
  return typeof v === "string" && /^[A-Za-z0-9_.:-]{1,1024}$/.test(v);
}
export function draftContext(v: unknown): v is DraftContext {
  return formBase(v) && v.kind === "draft" && signedToken(v.draft_token);
}
export function cancelContext(v: unknown): v is CancelContext {
  return (
    formBase(v) &&
    v.kind === "cancel" &&
    signedToken(v.confirmation) &&
    job(v.job) &&
    ["draft", "queued"].includes(v.job.status) &&
    object(v.workspace) &&
    v.job.workspace_id === v.workspace.id
  );
}
export function submitContext(v: unknown): v is SubmitContext {
  return (
    formBase(v) &&
    v.kind === "submit" &&
    signedToken(v.confirmation) &&
    job(v.job) &&
    v.job.status === "draft" &&
    object(v.workspace) &&
    v.job.workspace_id === v.workspace.id
  );
}

export type SourceConfiguration = {
  code: string;
  version: number;
  configured_enabled: boolean;
  configured_free_collection: boolean;
  metadata_limited: boolean;
  countries: string[] | null;
  categories: string[] | null;
  statuses: string[] | null;
  fields: string[] | null;
};
export type SourceCatalog = {
  workspace: { id: string; name: string };
  sources: SourceConfiguration[];
  truncated: boolean;
};
function capabilityValues(v: unknown): v is string[] | null {
  return (
    v === null ||
    (Array.isArray(v) &&
      v.length <= 100 &&
      v.every((s) => typeof s === "string" && s.length <= 120))
  );
}
export function sourceCatalog(v: unknown): v is SourceCatalog {
  return (
    object(v) &&
    object(v.workspace) &&
    uuid(v.workspace.id) &&
    typeof v.workspace.name === "string" &&
    v.workspace.name.length <= 120 &&
    typeof v.truncated === "boolean" &&
    Array.isArray(v.sources) &&
    v.sources.length <= 100 &&
    v.sources.every(
      (s) =>
        object(s) &&
        typeof s.code === "string" &&
        s.code.length <= 64 &&
        count(s.version) &&
        typeof s.configured_enabled === "boolean" &&
        typeof s.configured_free_collection === "boolean" &&
        typeof s.metadata_limited === "boolean" &&
        capabilityValues(s.countries) &&
        capabilityValues(s.categories) &&
        capabilityValues(s.statuses) &&
        capabilityValues(s.fields),
    )
  );
}

export const jobStates = [
  "draft",
  "queued",
  "running",
  "partial",
  "completed",
  "failed",
  "paused",
  "cancelled",
] as const;
export const jobState = (v: unknown): v is (typeof jobStates)[number] =>
  typeof v === "string" && jobStates.some((s) => s === v);

export type DraftFeedback = Omit<DraftContext, "kind"> & {
  kind: "draft-feedback";
  status: 400 | 409;
  values: {
    countries: string[];
    statuses: string[];
    required_fields: string[];
    categories: string;
    source_codes: string;
    result_limit: string;
  };
  errors: Record<string, string[]>;
};
export function draftFeedback(v: unknown): v is DraftFeedback {
  const strings = (a: unknown) =>
    Array.isArray(a) &&
    a.length <= 12 &&
    a.every((s) => typeof s === "string" && s.length <= 64);
  return (
    formBase(v) &&
    v.kind === "draft-feedback" &&
    signedToken(v.draft_token) &&
    [400, 409].includes(v.status as number) &&
    object(v.values) &&
    strings(v.values.countries) &&
    strings(v.values.statuses) &&
    strings(v.values.required_fields) &&
    typeof v.values.categories === "string" &&
    v.values.categories.length <= 1600 &&
    typeof v.values.source_codes === "string" &&
    v.values.source_codes.length <= 900 &&
    typeof v.values.result_limit === "string" &&
    v.values.result_limit.length <= 40 &&
    object(v.errors) &&
    Object.entries(v.errors).every(
      ([k, a]) =>
        [
          "countries",
          "statuses",
          "required_fields",
          "categories",
          "source_codes",
          "result_limit",
          "__all__",
        ].includes(k) &&
        Array.isArray(a) &&
        a.length <= 5 &&
        a.every((s) => typeof s === "string" && s.length <= 240),
    )
  );
}

export type SignOutContext = { kind: "sign-out"; csrf_token: string };
export function signOutContext(v: unknown): v is SignOutContext {
  return (
    object(v) &&
    v.kind === "sign-out" &&
    typeof v.csrf_token === "string" &&
    /^[A-Za-z0-9]{64}$/.test(v.csrf_token)
  );
}

export type SignInContext = {
  kind: "sign-in";
  csrf_token: string;
  signup_enabled?: boolean;
};
export function signInContext(v: unknown): v is SignInContext {
  return (
    object(v) &&
    v.kind === "sign-in" &&
    typeof v.csrf_token === "string" &&
    /^[A-Za-z0-9]{64}$/.test(v.csrf_token) &&
    (v.signup_enabled === undefined || typeof v.signup_enabled === "boolean")
  );
}

export const resultFieldNames = [
  "business_name",
  "phone",
  "city",
  "website",
  "status",
  "address",
] as const;
export type SavedResult = {
  id: string;
  country: string;
  category: string;
  fields: Partial<Record<(typeof resultFieldNames)[number], string>> & {
    business_name: string;
    phone: string;
  };
  source_code: string;
  policy_version: number;
  observed_at: string;
  delete_at: string;
  retention_version: string;
  provenance_fields: string[];
};
type ResultFilterMetadata = {
  country: "" | "US" | "CA";
  category_filter: string;
  source_filter: string;
  category_options: string[];
  source_options: string[];
};
function resultFilterMetadata(
  v: unknown,
): v is ResultFilterMetadata & Record<string, unknown> {
  if (!object(v) || !["", "US", "CA"].includes(v.country as string))
    return false;
  for (const [key, optionsKey, maximum] of [
    ["category_filter", "category_options", 120],
    ["source_filter", "source_options", 64],
  ] as const) {
    const selected = v[key],
      options = v[optionsKey];
    if (
      typeof selected !== "string" ||
      (selected !== "" && !/^(?:[0-9]|1[01])$/.test(selected)) ||
      !Array.isArray(options) ||
      options.length > 12 ||
      new Set(options).size !== options.length ||
      !options.every(
        (label) =>
          typeof label === "string" &&
          label.trim().length > 0 &&
          label.length <= maximum &&
          !/[\x00-\x1f\x7f]/.test(label),
      ) ||
      (selected !== "" && Number(selected) >= options.length)
    )
      return false;
  }
  return true;
}
export type SavedResults = ResultFilterMetadata & {
  workspace_id: string;
  job_id: string;
  results: SavedResult[];
  withheld_count: number;
  filtered_count: number;
  can_review_export: boolean;
  can_review_receipts: boolean;
};
export function savedResults(v: unknown): v is SavedResults {
  return (
    object(v) &&
    uuid(v.workspace_id) &&
    uuid(v.job_id) &&
    typeof v.can_review_export === "boolean" &&
    typeof v.can_review_receipts === "boolean" &&
    count(v.filtered_count) &&
    resultFilterMetadata(v) &&
    count(v.withheld_count) &&
    v.withheld_count <= 25 &&
    Array.isArray(v.results) &&
    v.results.length <= 25 &&
    v.results.length + v.withheld_count + v.filtered_count <= 25 &&
    v.results.every(
      (r) =>
        object(r) &&
        uuid(r.id) &&
        typeof r.country === "string" &&
        ["US", "CA"].includes(r.country) &&
        (!v.country || r.country === v.country) &&
        (!v.category_filter ||
          r.category === v.category_options[Number(v.category_filter)]) &&
        (!v.source_filter ||
          r.source_code === v.source_options[Number(v.source_filter)]) &&
        typeof r.category === "string" &&
        r.category.length <= 120 &&
        object(r.fields) &&
        typeof r.fields.business_name === "string" &&
        typeof r.fields.phone === "string" &&
        Object.entries(r.fields).every(
          ([k, val]) =>
            resultFieldNames.includes(k as (typeof resultFieldNames)[number]) &&
            typeof val === "string" &&
            val.trim().length > 0 &&
            val.length <= 2000,
        ) &&
        typeof r.source_code === "string" &&
        r.source_code.length <= 64 &&
        count(r.policy_version) &&
        r.policy_version > 0 &&
        typeof r.retention_version === "string" &&
        r.retention_version.length <= 64 &&
        typeof r.observed_at === "string" &&
        Number.isFinite(Date.parse(r.observed_at)) &&
        typeof r.delete_at === "string" &&
        Number.isFinite(Date.parse(r.delete_at)) &&
        Array.isArray(r.provenance_fields) &&
        r.provenance_fields.length <= 6 &&
        r.provenance_fields.every(
          (f: unknown) =>
            typeof f === "string" && Object.hasOwn(r.fields as object, f),
        ),
    )
  );
}

export type ExportContext = ResultFilterMetadata & {
  records: { id: string; business_name: string; country: "US" | "CA" }[];
  kind: "export";
  workspace_id: string;
  job_id: string;
  csrf_token: string;
  confirmation: string;
  fields: string[];
  omitted_fields: string[];
  record_count: number;
  withheld_count: number;
  filtered_count: number;
  expires_at: string;
  sources: { code: string; attribution: string }[];
};
export function exportContext(v: unknown): v is ExportContext {
  const fields = (value: unknown): value is string[] =>
    Array.isArray(value) &&
    value.length <= 6 &&
    new Set(value).size === value.length &&
    value.every(
      (f) =>
        typeof f === "string" &&
        resultFieldNames.includes(f as (typeof resultFieldNames)[number]),
    );
  return (
    object(v) &&
    v.kind === "export" &&
    uuid(v.workspace_id) &&
    uuid(v.job_id) &&
    typeof v.csrf_token === "string" &&
    /^[A-Za-z0-9]{64}$/.test(v.csrf_token) &&
    typeof v.confirmation === "string" &&
    v.confirmation.length > 0 &&
    v.confirmation.length <= 4096 &&
    fields(v.fields) &&
    v.fields.length > 0 &&
    fields(v.omitted_fields) &&
    count(v.record_count) &&
    v.record_count > 0 &&
    v.record_count <= 25 &&
    Array.isArray(v.records) &&
    v.records.length === v.record_count &&
    new Set(v.records.map((r: unknown) => (object(r) ? r.id : null))).size ===
      v.records.length &&
    v.records.every(
      (r: unknown) =>
        object(r) &&
        uuid(r.id) &&
        typeof r.business_name === "string" &&
        r.business_name.length > 0 &&
        r.business_name.length <= 2000 &&
        (r.country === "US" || r.country === "CA") &&
        (!v.country || r.country === v.country),
    ) &&
    count(v.filtered_count) &&
    resultFilterMetadata(v) &&
    count(v.withheld_count) &&
    v.withheld_count + v.record_count + v.filtered_count <= 25 &&
    typeof v.expires_at === "string" &&
    Number.isFinite(Date.parse(v.expires_at)) &&
    Array.isArray(v.sources) &&
    v.sources.length > 0 &&
    v.sources.length <= 12 &&
    v.sources.every(
      (s) =>
        object(s) &&
        typeof s.code === "string" &&
        s.code.length <= 64 &&
        typeof s.attribution === "string" &&
        s.attribution.length <= 240,
    )
  );
}

export type ExportReceipts = {
  workspace_id: string;
  job_id: string;
  scope: "job" | "own";
  receipts: {
    id: string;
    record_count: number;
    export_units: 1;
    prepared_at: string;
    retention_deadline: string;
    deadline_passed: boolean;
  }[];
  next_cursor: string | null;
};
export function receiptCursor(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= 1024 &&
    /^[A-Za-z0-9_:-]+$/.test(value)
  );
}
export function exportReceipts(v: unknown): v is ExportReceipts {
  return (
    object(v) &&
    uuid(v.workspace_id) &&
    uuid(v.job_id) &&
    (v.scope === "job" || v.scope === "own") &&
    (v.next_cursor === null || receiptCursor(v.next_cursor)) &&
    Array.isArray(v.receipts) &&
    v.receipts.length <= 25 &&
    new Set(v.receipts.map((r: unknown) => (object(r) ? r.id : null))).size ===
      v.receipts.length &&
    v.receipts.every(
      (r: unknown) =>
        object(r) &&
        uuid(r.id) &&
        count(r.record_count) &&
        r.record_count >= 1 &&
        r.record_count <= 25 &&
        r.export_units === 1 &&
        typeof r.deadline_passed === "boolean" &&
        typeof r.prepared_at === "string" &&
        Number.isFinite(Date.parse(r.prepared_at)) &&
        typeof r.retention_deadline === "string" &&
        Number.isFinite(Date.parse(r.retention_deadline)),
    )
  );
}
