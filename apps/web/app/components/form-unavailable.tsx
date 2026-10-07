import { backendLink } from "../../lib/backend";
import { State } from "./state";
export function FormUnavailable({ kind }: { kind: string }) {
  return (
    <>
      <State kind={kind} />
      <p>
        If your session needs a form cookie,{" "}
        <a href={backendLink("/accounts/check-session/")}>check your session</a>{" "}
        and open the form again. Your current role and job state must allow this
        action.
      </p>
    </>
  );
}
