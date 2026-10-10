"use client";

import Link from "next/link";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <section role="alert" aria-labelledby="page-error-title">
      <h1 id="page-error-title">This page could not be displayed.</h1>
      <p>
        The request could not be completed. Retrying does not authorize a
        payment, create a search job or confirm that any previous action failed.
        Review your workspace state before repeating a submitted action.
      </p>
      <div className="actions">
        <button type="button" onClick={reset}>
          Retry loading page
        </button>
        <Link href="/">Return to home</Link>
      </div>
    </section>
  );
}
