"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <>
      <h1>Something went wrong</h1>
      <p>Please try again.</p>
      <button onClick={reset}>Retry</button>
    </>
  );
}
