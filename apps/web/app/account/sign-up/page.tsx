import Link from "next/link";
import { notFound } from "next/navigation";
import { backend, backendLink } from "../../../lib/backend";
import { signInContext } from "../../../lib/contracts";
const notices: Record<string, string> = {
  invalid:
    "We could not create the account. Use a password of at least 8 characters that is not too common or similar to your username, and type it the same way twice.",
  taken: "That username is already in use. Choose another or sign in.",
  limited: "Too many attempts. Wait 15 minutes before trying again.",
};
export default async function SignUp({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string | string[] }>;
}) {
  const { notice } = await searchParams;
  if (
    notice !== undefined &&
    !(typeof notice === "string" && notice in notices)
  )
    notFound();
  const result = await backend("/api/v1/account/sign-in-form/", signInContext);
  if (result.kind === "ok" && !result.data.signup_enabled) notFound();
  return (
    <>
      <h1>Create account</h1>
      <p>Your account gets its own workspace for saved searches and leads.</p>
      {notice ? (
        <p className="notice" role="alert">
          {notices[notice as string]}
        </p>
      ) : null}
      {result.kind === "ok" ? (
        <form
          className="card search-form"
          method="post"
          action={backendLink("/accounts/sign-up/")}
        >
          <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={result.data.csrf_token}
          />
          <input type="hidden" name="native_signup" value="1" />
          <label htmlFor="username">Username</label>
          <input
            id="username"
            name="username"
            maxLength={150}
            autoComplete="username"
            required
          />
          <label htmlFor="workspace_name">Workspace name (optional)</label>
          <input id="workspace_name" name="workspace_name" maxLength={120} />
          <label htmlFor="password1">Password</label>
          <input
            id="password1"
            name="password1"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
          />
          <label htmlFor="password2">Confirm password</label>
          <input
            id="password2"
            name="password2"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
          />
          <button className="button" type="submit">
            Create account
          </button>
        </form>
      ) : (
        <section className="card">
          <p>Prepare this browser before creating an account.</p>
          <a className="button" href={backendLink("/accounts/start-sign-in/")}>
            Prepare browser
          </a>
        </section>
      )}
      <p>
        <Link href="/account/sign-in">Already have an account? Sign in</Link>
      </p>
    </>
  );
}
