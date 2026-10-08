export type ResultFilters = {
  country: "" | "US" | "CA";
  category: string;
  source: string;
};
export function resultFilters(
  query: Record<string, string | string[] | undefined>,
): ResultFilters | null {
  if (
    Object.keys(query).some(
      (key) => !["country", "category", "source"].includes(key),
    )
  )
    return null;
  const country = query.country ?? "";
  const category = query.category ?? "";
  const source = query.source ?? "";
  if (country !== "" && country !== "US" && country !== "CA") return null;
  if (typeof category !== "string" || typeof source !== "string") return null;
  if ([category, source].some((v) => v !== "" && !/^(?:[0-9]|1[01])$/.test(v)))
    return null;
  return { country, category, source };
}
export function resultFilterQuery(filters: ResultFilters): string {
  const query = new URLSearchParams();
  for (const key of ["country", "category", "source"] as const) {
    if (filters[key]) query.set(key, filters[key]);
  }
  return query.size ? `?${query.toString()}` : "";
}
