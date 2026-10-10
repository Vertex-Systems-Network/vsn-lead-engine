// Only trusted server configuration chooses the destination. No browser proxy.
export function trustedOrigin(value) {
  const url = new URL(value);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    url.pathname !== "/" ||
    (url.protocol !== "https:" && !(local && url.protocol === "http:"))
  ) {
    throw new Error("Invalid backend origin");
  }
  return url.origin;
}
const filteredJobsPath =
  /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/jobs\/\?status=(?:draft|queued|running|partial|completed|failed|paused|cancelled)(?:&after=[0-9a-f-]{36})?$/;
const resultFilterQuery =
  /^(?:country=(?:US|CA)(?:&category=(?:[0-9]|1[01]))?(?:&source=(?:[0-9]|1[01]))?|category=(?:[0-9]|1[01])(?:&source=(?:[0-9]|1[01]))?|source=(?:[0-9]|1[01]))$/;
function filteredResultPath(path, suffix) {
  const [base, query, extra] = path.split("?");
  return (
    extra === undefined &&
    /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/jobs\/[0-9a-f-]{36}\/(?:results|export-form)\/$/.test(
      base,
    ) &&
    base.endsWith(`/${suffix}/`) &&
    (query === undefined || resultFilterQuery.test(query))
  );
}
const workspaceDetailPath = /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/$/;
const jobSummaryPath = /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/job-summary\/$/;

const dailyPlansPath =
  /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/daily-plans\/(?:\?after=[0-9a-f-]{36})?$/;
const membersPath =
  /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/members\/(?:\?page=[1-9][0-9]{0,5})?$/;
const formPath =
  /^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/(?:draft-form\/|draft-feedback\/[0-9a-f-]{36}\/|jobs\/[0-9a-f-]{36}\/(?:cancel-form|submit-form|export-form)\/)$/;
export async function readBackend(
  origin,
  path,
  session,
  fetcher = fetch,
  csrf,
) {
  const publicForm = path === "/api/v1/account/sign-in-form/";
  const form =
    publicForm ||
    formPath.test(path) ||
    filteredResultPath(path, "export-form") ||
    path === "/api/v1/account/sign-out-form/";
  if (
    !form &&
    !workspaceDetailPath.test(path) &&
    !jobSummaryPath.test(path) &&
    !dailyPlansPath.test(path) &&
    !membersPath.test(path) &&
    !filteredJobsPath.test(path) &&
    !/^\/api\/v1\/workspaces\/[0-9a-f-]{36}\/jobs\/[0-9a-f-]{36}\/export-receipts\/(?:\?after=[A-Za-z0-9_:%-]{1,1200})?$/.test(
      path,
    ) &&
    !filteredResultPath(path, "results") &&
    !/^\/api\/v1\/workspaces\/(?:[0-9a-f-]{36}\/(?:usage\/|sources\/|jobs\/(?:[0-9a-f-]{36}\/)?))?(?:\?(?:page=[1-9][0-9]{0,5}|after=[0-9a-f-]{36}))?$/.test(
      path,
    )
  ) {
    throw new Error("Unsupported backend path");
  }
  if (!publicForm && !/^[a-z0-9]{32}$/.test(session ?? ""))
    return { kind: "signin" };
  if (form && !/^[A-Za-z0-9]{32}$/.test(csrf ?? "")) return { kind: "denied" };
  try {
    const response = await fetcher(new URL(path, trustedOrigin(origin)), {
      headers: {
        Accept: "application/json",
        Cookie: publicForm
          ? `csrftoken=${csrf}`
          : `sessionid=${session}${form ? `; csrftoken=${csrf}` : ""}`,
      },
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(5000),
    });
    if (response.status === 401 || response.status === 403)
      return { kind: "denied" };
    if (response.status === 404) return { kind: "missing" };
    if (
      !response.ok ||
      !response.headers.get("content-type")?.includes("application/json")
    )
      return { kind: "unavailable" };
    if (!response.body) return { kind: "unavailable" };
    const reader = response.body.getReader();
    const chunks = [];
    let size = 0;
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        size += part.value.byteLength;
        if (size > 131072) {
          await reader.cancel();
          return { kind: "unavailable" };
        }
        chunks.push(part.value);
      }
    } finally {
      reader.releaseLock();
    }
    const data = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      data.set(chunk, offset);
      offset += chunk.length;
    }
    return { kind: "ok", data: JSON.parse(new TextDecoder().decode(data)) };
  } catch {
    return { kind: "unavailable" };
  }
}
