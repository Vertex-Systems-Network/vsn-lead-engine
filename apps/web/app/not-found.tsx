import Link from "next/link";

export default function Missing() {
  return (
    <section
      className="marketing marketing-detail"
      aria-labelledby="missing-title"
    >
      <div className="marketing-page-intro">
        <p className="marketing-kicker">
          Page not found · SaaS development preview
        </p>
        <h1 id="missing-title">This page is unavailable.</h1>
        <p className="marketing-lead">
          The address may have changed, or this feature may not exist in the
          current development build. This does not mean a workspace or customer
          record has been found or deleted.
        </p>
        <p className="marketing-disclosure">
          Public SaaS access has not launched. No account information is
          displayed on this page.
        </p>
        <div className="marketing-actions">
          <Link className="marketing-primary" href="/">
            Return to home
          </Link>
          <Link className="marketing-secondary" href="/capabilities">
            Review capabilities
          </Link>
          <Link className="marketing-secondary" href="/faq">
            Frequently asked questions
          </Link>
        </div>
      </div>
    </section>
  );
}
