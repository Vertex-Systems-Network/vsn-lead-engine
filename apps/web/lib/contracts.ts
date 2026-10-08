export const uuid = (value: unknown): value is string =>
  typeof value === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const object = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const count = (v: unknown): v is number =>
  typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
export type Workspace = { id: string; name: string; timezone: string };
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
    v.results.every(
      (w) =>
        object(w) &&
        uuid(w.id) &&
        typeof w.name === "string" &&
        typeof w.timezone === "string",
    )
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

export type SignInContext = { kind: "sign-in"; csrf_token: string };
export function signInContext(v: unknown): v is SignInContext {
  return (
    object(v) &&
    v.kind === "sign-in" &&
    typeof v.csrf_token === "string" &&
    /^[A-Za-z0-9]{64}$/.test(v.csrf_token)
  );
}
