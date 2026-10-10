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
export const dueDiagnosticStatuses = [
  "disabled",
  "invalid_configuration",
  "creator_not_authorized",
  "entitlement_not_current",
  "candidate_due_requires_execution_gates",
  "no_unmaterialized_due_day",
] as const;
export type DueDiagnostic = {
  id: string;
  enabled: boolean;
  revision: number;
  status: (typeof dueDiagnosticStatuses)[number];
  due_local_dates: { local_date: string; resolution: string }[];
};
export type DueDiagnostics = {
  workspace_id: string;
  as_of_utc: string;
  total_plans: number;
  inspected: number;
  next: string | null;
  advisory_only: true;
  requires_execution_gates: string[];
  plans: DueDiagnostic[];
};
export function dueDiagnostics(v: unknown): v is DueDiagnostics {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    typeof v.as_of_utc !== "string" ||
    !Number.isFinite(Date.parse(v.as_of_utc)) ||
    !count(v.total_plans) ||
    !count(v.inspected) ||
    v.inspected > 25 ||
    v.inspected > v.total_plans ||
    (v.next !== null && !uuid(v.next)) ||
    v.advisory_only !== true ||
    !Array.isArray(v.requires_execution_gates) ||
    !Array.isArray(v.plans) ||
    v.plans.length !== v.inspected
  )
    return false;
  const executionGates = v.requires_execution_gates;
  if (
    ![
      "fresh_membership",
      "entitlement_capacity",
      "source_rights",
      "provider_credentials",
      "operator_release",
    ].every((gate) => executionGates.includes(gate))
  )
    return false;
  return (
    new Set(v.plans.map((p: unknown) => (object(p) ? p.id : null))).size ===
      v.plans.length &&
    v.plans.every(
      (p: unknown) =>
        object(p) &&
        uuid(p.id) &&
        typeof p.enabled === "boolean" &&
        count(p.revision) &&
        p.revision >= 1 &&
        dueDiagnosticStatuses.some((s) => s === p.status) &&
        Array.isArray(p.due_local_dates) &&
        p.due_local_dates.length <= 7 &&
        p.due_local_dates.every(
          (date: unknown) =>
            object(date) &&
            typeof date.local_date === "string" &&
            /^\d{4}-\d{2}-\d{2}$/.test(date.local_date) &&
            [
              "normal",
              "gap_forward",
              "ambiguous_earlier",
              "skipped_day",
            ].includes(String(date.resolution)),
        ),
    )
  );
}

export const planReadinessCheckNames = [
  "stored_plan_snapshot",
  "creator_membership",
  "entitlement_current",
  "explicit_source_selection",
  "internal_source_catalog_match",
] as const;
export const planReadinessExternalGates = [
  "current_usable_quota",
  "source_commercial_rights",
  "provider_credentials_and_health",
  "scheduler_fencing_and_observability",
  "operator_release_and_deployment",
] as const;
export type PlanReadiness = {
  workspace_id: string;
  plan_id: string;
  stored_enabled: boolean;
  advisory_only: true;
  status: "blocked" | "internal_catalog_match_only";
  checked_source_count: number;
  checks: {
    name: (typeof planReadinessCheckNames)[number];
    status: "pass" | "blocked";
  }[];
  unverified_execution_gates: string[];
};
export function planReadiness(v: unknown): v is PlanReadiness {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    !uuid(v.plan_id) ||
    typeof v.stored_enabled !== "boolean" ||
    v.advisory_only !== true ||
    !["blocked", "internal_catalog_match_only"].includes(String(v.status)) ||
    !count(v.checked_source_count) ||
    v.checked_source_count > 12 ||
    !Array.isArray(v.checks) ||
    v.checks.length !== planReadinessCheckNames.length ||
    !Array.isArray(v.unverified_execution_gates) ||
    v.unverified_execution_gates.length !== planReadinessExternalGates.length
  )
    return false;
  const checks = v.checks;
  const externalGates = v.unverified_execution_gates;
  return (
    planReadinessCheckNames.every((name) =>
      checks.some(
        (item: unknown) =>
          object(item) &&
          item.name === name &&
          ["pass", "blocked"].includes(String(item.status)),
      ),
    ) &&
    new Set(checks.map((item: unknown) => (object(item) ? item.name : null))).size ===
      planReadinessCheckNames.length &&
    planReadinessExternalGates.every((name) => externalGates.includes(name)) &&
    new Set(externalGates).size === planReadinessExternalGates.length &&
    (v.status === "blocked") ===
      checks.some((item: unknown) => object(item) && item.status === "blocked")
  );
}

export type DailyPlan = {
  id: string;
  timezone: string;
  local_time: string;
  enabled: boolean;
  revision: number;
  created_at: string;
};
export type DailyPlans = {
  workspace_id: string;
  total: number;
  results: DailyPlan[];
  next: string | null;
};
export function dailyPlans(v: unknown): v is DailyPlans {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    !count(v.total) ||
    (v.next !== null && !uuid(v.next)) ||
    !Array.isArray(v.results) ||
    v.results.length > 25 ||
    v.results.length > v.total
  )
    return false;
  return (
    new Set(v.results.map((row: unknown) => (object(row) ? row.id : null)))
      .size === v.results.length &&
    v.results.every(
      (row: unknown) =>
        object(row) &&
        uuid(row.id) &&
        typeof row.timezone === "string" &&
        row.timezone.length > 0 &&
        row.timezone.length <= 64 &&
        typeof row.local_time === "string" &&
        /^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(row.local_time) &&
        typeof row.enabled === "boolean" &&
        count(row.revision) &&
        row.revision >= 1 &&
        typeof row.created_at === "string" &&
        Number.isFinite(Date.parse(row.created_at)),
    )
  );
}

export type DailyPlanDetail = DailyPlan & {
  workspace_id: string;
  search: {
    countries: string[];
    categories: string[];
    statuses: string[];
    required_fields: string[];
    source_codes: string[];
    result_limit: number;
  };
};
export function dailyPlanDetail(v: unknown): v is DailyPlanDetail {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    !dailyPlans({
      workspace_id: v.workspace_id,
      total: 1,
      results: [v],
      next: null,
    }) ||
    !object(v.search)
  )
    return false;
  const s = v.search;
  return (
    Array.isArray(s.countries) &&
    s.countries.length >= 1 &&
    s.countries.length <= 2 &&
    s.countries.every((x) => x === "US" || x === "CA") &&
    Array.isArray(s.categories) &&
    s.categories.length >= 1 &&
    s.categories.length <= 12 &&
    s.categories.every((x) => typeof x === "string" && x.length <= 120) &&
    Array.isArray(s.statuses) &&
    s.statuses.length <= 3 &&
    s.statuses.every((x) => ["active", "closed", "opening_soon"].includes(x)) &&
    Array.isArray(s.required_fields) &&
    s.required_fields.length <= 4 &&
    s.required_fields.every((x) =>
      ["phone", "name", "website", "address"].includes(x),
    ) &&
    Array.isArray(s.source_codes) &&
    s.source_codes.length <= 12 &&
    s.source_codes.every((x) => typeof x === "string" && x.length <= 64) &&
    count(s.result_limit) &&
    s.result_limit >= 1 &&
    s.result_limit <= 1000
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

export type JobStatusSummary = {
  workspace_id: string;
  total: number;
  statuses: Record<(typeof jobStates)[number], number>;
};
export function jobStatusSummary(v: unknown): v is JobStatusSummary {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    !count(v.total) ||
    !object(v.statuses)
  )
    return false;
  const values = v.statuses;
  return (
    Object.keys(values).length === jobStates.length &&
    jobStates.every((state) => count(values[state])) &&
    jobStates.reduce((sum, state) => sum + Number(values[state]), 0) === v.total
  );
}

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

export type DailyOccurrence = {
  id: string;
  local_date: string;
  local_time: string;
  timezone: string;
  schedule_revision: number;
  resolution: "normal" | "gap_forward" | "ambiguous_earlier" | "skipped_day";
  scheduled_for: string | null;
  job_id: string | null;
  job_status: (typeof jobStates)[number] | null;
};
export type DailyOccurrenceHistory = {
  workspace_id: string;
  plan_id: string;
  total: number;
  results: DailyOccurrence[];
  next: string | null;
  advisory_only: true;
};
export function dailyOccurrenceHistory(
  v: unknown,
): v is DailyOccurrenceHistory {
  if (
    !object(v) ||
    !uuid(v.workspace_id) ||
    !uuid(v.plan_id) ||
    !count(v.total) ||
    v.advisory_only !== true ||
    !Array.isArray(v.results) ||
    v.results.length > 25 ||
    v.results.length > v.total ||
    (v.next !== null &&
      (typeof v.next !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v.next)))
  )
    return false;
  if (
    !v.results.every(
      (r: unknown) =>
        object(r) &&
        uuid(r.id) &&
        typeof r.local_date === "string" &&
        /^\d{4}-\d{2}-\d{2}$/.test(r.local_date) &&
        Number.isFinite(Date.parse(r.local_date)) &&
        typeof r.local_time === "string" &&
        /^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(r.local_time) &&
        typeof r.timezone === "string" &&
        r.timezone.length > 0 &&
        r.timezone.length <= 64 &&
        count(r.schedule_revision) &&
        r.schedule_revision >= 1 &&
        ["normal", "gap_forward", "ambiguous_earlier", "skipped_day"].includes(
          String(r.resolution),
        ) &&
        (r.scheduled_for === null ||
          (typeof r.scheduled_for === "string" &&
            Number.isFinite(Date.parse(r.scheduled_for)))) &&
        (r.job_id === null || uuid(r.job_id)) &&
        (r.job_status === null || jobState(r.job_status)) &&
        (r.job_id === null ? r.job_status === null : r.job_status !== null) &&
        (r.resolution === "skipped_day"
          ? r.scheduled_for === null && r.job_id === null
          : r.scheduled_for !== null && r.job_id !== null),
    )
  )
    return false;
  const dates = v.results.map((row: DailyOccurrence) => row.local_date);
  return (
    new Set(dates).size === dates.length &&
    dates.every((d, i) => i === 0 || dates[i - 1] > d) &&
    (v.next === null ||
      (dates.length > 0 && v.next === dates[dates.length - 1]))
  );
}
