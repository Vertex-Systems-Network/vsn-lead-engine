import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "VSN Lead Engine",
  description: "VSN Lead Engine development preview: tenant-scoped business search workflows.",
};

export default function Layout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header>
          <Link href="/" className="brand">VSN <span>Lead Engine</span></Link>
          <nav className="site-nav" aria-label="Primary navigation">
            <Link href="/">Home</Link>
            <Link href="/capabilities">Capabilities</Link>
            <Link href="/plans">Plans</Link>
            <Link href="/data-handling">Data handling</Link>
            <Link href="/dashboard">Dashboard</Link>
          </nav>
          <span className="badge">Development</span>
        </header>
        <main id="main">{children}</main>
        <footer>US &amp; Canada · SaaS development preview · Public service not launched</footer>
      </body>
    </html>
  );
}
