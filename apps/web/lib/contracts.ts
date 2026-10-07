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
