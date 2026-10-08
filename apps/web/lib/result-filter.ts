export function resultCountry(
  query: Record<string, string | string[] | undefined>,
): "" | "US" | "CA" | null {
  if (Object.keys(query).some((key) => key !== "country")) return null;
  const country = query.country ?? "";
  return country === "" || country === "US" || country === "CA"
    ? country
    : null;
}
