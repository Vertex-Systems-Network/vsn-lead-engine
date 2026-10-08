import Link from "next/link";
export function State({ kind }: { kind: string }) {
  const message =
    kind === "signin"
      ? "Sign in to see your workspaces."
      : kind === "denied"
        ? "Your session has expired or you do not have access."
        : kind === "missing"
          ? "This workspace or job is unavailable."
          : "We could not load this information. Please try again.";
  return (
    <section className="card">
      <h1>
        {kind === "signin"
          ? "Welcome to your workspace"
          : "Information unavailable"}
      </h1>
      <p>{message}</p>
      <Link className="button" href="/account/sign-in" prefetch={false}>
        Sign in
      </Link>
      <p className="muted">Sign in opens the secure account screen.</p>
    </section>
  );
}
