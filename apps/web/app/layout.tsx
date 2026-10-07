import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
export const metadata: Metadata = {
  title: "VSN Lead Engine",
  description: "Workspace lead operations",
};
export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        <header>
          <Link href="/dashboard" className="brand">
            VSN <span>Lead Engine</span>
          </Link>
          <span className="badge">Development</span>
        </header>
        <main id="main">{children}</main>
        <footer>
          US & Canada · Phone-qualified leads · Collection is currently
          unavailable
        </footer>
      </body>
    </html>
  );
}
