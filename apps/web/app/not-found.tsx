import Link from "next/link";
export default function Missing() {
  return (
    <>
      <h1>Page unavailable</h1>
      <Link href="/dashboard">Return to workspaces</Link>
    </>
  );
}
