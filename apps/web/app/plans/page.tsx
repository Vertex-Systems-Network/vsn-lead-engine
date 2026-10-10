import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Plans and availability | VSN Lead Engine",
  description:
    "Subscriptions are not on sale. Review preliminary VSN Lead Engine plan concepts without payment or price claims.",
};
const concepts = [
  [
    "Individual",
    "Single-workspace workflows",
    "Manual search and lead review are the first development focus.",
  ],
  [
    "Team",
    "Collaborative workspaces",
    "Role-based access exists; invitations, billing seats and operational controls need more development.",
  ],
  [
    "Custom",
    "Specialized sources and workflows",
    "BYOK, paid providers and custom integrations depend on separate rights, cost and architecture reviews.",
  ],
];
export default function Plans() {
  return (
    <div className="marketing marketing-detail">
      <section className="marketing-page-intro">
        <p className="marketing-kicker">Plans and availability</p>
        <h1>Subscriptions are not yet on sale.</h1>
        <p className="marketing-lead">
          Pricing, trials, payments, quotas and included credits are not
          finalized. These are possible product directions, not purchasable
          packages.
        </p>
        <p className="marketing-disclosure">
          This page has no checkout, upgrade action, trial enrollment or payment
          collection.
        </p>
      </section>
      <section className="marketing-section" aria-labelledby="concepts-title">
        <div className="marketing-section-head">
          <p className="marketing-kicker">Unpriced concepts</p>
          <h2 id="concepts-title">Possible ways to use the platform</h2>
        </div>
        <div className="marketing-cards">
          {concepts.map(([title, subtitle, detail]) => (
            <article className="marketing-card" key={title}>
              <span className="marketing-tag">Concept · not for sale</span>
              <h3>{title}</h3>
              <p>
                <strong>{subtitle}</strong>
              </p>
              <p>{detail}</p>
              <p className="marketing-card-foot">
                Price and limits: not published
              </p>
            </article>
          ))}
        </div>
      </section>
      <section className="marketing-closing">
        <div>
          <h2>Explore what exists in the development build.</h2>
          <p>
            Release readiness, providers and account availability are separate
            gates.
          </p>
        </div>
        <div className="marketing-actions">
          <Link className="marketing-primary" href="/capabilities">
            Review capabilities
          </Link>
          <Link className="marketing-secondary" href="/">
            Back to home
          </Link>
        </div>
      </section>
    </div>
  );
}
