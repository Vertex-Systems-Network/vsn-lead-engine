import "server-only";
import { cookies } from "next/headers";
import { readBackend, trustedOrigin } from "./transport.mjs";
export type Result<T> =
  | { kind: "ok"; data: T }
  | { kind: "signin" | "denied" | "missing" | "unavailable" };
export function backendLink(path: string) {
  return new URL(
    path,
    trustedOrigin(process.env.SAAS_PUBLIC_ORIGIN ?? "http://localhost:8000"),
  ).href;
}
export async function backend<T>(
  path: string,
  validate: (value: unknown) => value is T,
): Promise<Result<T>> {
  const session = (await cookies()).get("sessionid")?.value;
  const result = await readBackend(
    process.env.SAAS_BACKEND_ORIGIN ?? "http://localhost:8000",
    path,
    session,
  );
  if (result.kind !== "ok") return result as Result<T>;
  return validate(result.data)
    ? { kind: "ok", data: result.data }
    : { kind: "unavailable" };
}
