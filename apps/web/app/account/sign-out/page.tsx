import Link from "next/link";
import { backend, backendLink } from "../../../lib/backend";
import { signOutContext } from "../../../lib/contracts";
import { FormUnavailable } from "../../components/form-unavailable";
export default async function SignOut() {
  const result = await backend(
    "/api/v1/account/sign-out-form/",
    signOutContext,
  );
  if (result.kind !== "ok") return <FormUnavailable kind={result.kind} />;
  return (
    <>
      <h1>End your session</h1>
      <p>
        Sign out of this account on this browser. Your saved workspaces and
        searches remain available when you sign in again.
      </p>
      <form
        method="post"
        action={backendLink("/accounts/logout/")}
        className="card"
      >
        <input
          type="hidden"
          name="csrfmiddlewaretoken"
          value={result.data.csrf_token}
        />
        <button className="button" type="submit">
          Sign out
        </button>
        <Link href="/dashboard">Keep working</Link>
      </form>
    </>
  );
}
