import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../lib/backend";
import { signInContext } from "../../../lib/contracts";
export default async function SignIn({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string | string[] }>;
}) {
  const { notice } = await searchParams;
  if (notice !== undefined && notice !== "invalid" && notice !== "limited")
    notFound();
  const result = await backend("/api/v1/account/sign-in-form/", signInContext);
  return (
    <>
      <h1>Sign in</h1>
      <p>Access your saved workspaces and searches.</p>
      {notice ? (
        <p className="notice" role="alert">
          {notice === "limited"
            ? "Too many sign-in attempts. Wait 15 minutes before trying again."
            : "We could not sign you in. Check your details and try again."}
        </p>
      ) : null}
      {result.kind === "ok" ? (
        <form
          className="card search-form"
          method="post"
          action={backendLink("/accounts/login/")}
        >
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={result.data.csrf_token}
          />
          <input type="hidden" name="native_login" value="1" />
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            maxLength={150}
            autoComplete="username"
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
          />
          <button className="button" type="submit">
            Sign in
          </button>
          <p>
            <a href={backendLink("/accounts/password-reset/")}>
              Forgot your password?
            </a>
          </p>
          {result.data.signup_enabled ? (
            <p>
              New here? <Link href="/account/sign-up">Create an account</Link>
            </p>
          ) : null}
        </form>
      ) : (
        <section className="card">
          <p>
            {result.kind === "denied"
              ? "Prepare this browser before signing in."
              : "We could not prepare the sign-in form. Try again or open the account form."}
          </p>
          <a className="button" href={backendLink("/accounts/start-sign-in/")}>
            Start sign-in
          </a>
          <p>
            <a href={backendLink("/accounts/login/")}>Open account form</a>
          </p>
        </section>
      )}
      <p>
        <Link href="/dashboard">Back to dashboard</Link>
      </p>
    </>
  );
}
