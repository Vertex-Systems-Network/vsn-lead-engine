import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "VSN Lead Engine | Business lead workflows",
  description:
    "Explore VSN Lead Engine development features and its launch roadmap.",
};

const steps = [
  [
    "01",
    "Choose your scope",
    "Set supported countries, categories and required contact fields.",
  ],
  [
    "02",
    "Review source eligibility",
    "Check current source policy, permissions and hard usage limits.",
  ],
  [
    "03",
    "Review results",
    "Follow job progress and inspect records before a guarded export.",
  ],
];

export default function Home() {
  return (
    <div className="marketing">
      <section className="marketing-hero" aria-labelledby="marketing-title">
        <div>
          <p className="marketing-kicker">
            VSN Lead Engine · SaaS development preview
          </p>
          <h1 id="marketing-title">
            A clearer path from business search to lead review.
          </h1>
          <p className="marketing-lead">
            Define a search, review eligible sources, follow job progress and
            work with accepted records from a tenant-scoped workspace. Built
            around US and Canada development use cases.
          </p>
          <div className="marketing-actions">
            <Link className="marketing-primary" href="/capabilities">
              Explore capabilities <span aria-hidden="true">↗</span>
            </Link>
            <Link className="marketing-secondary" href="/account/sign-in">
              Development sign-in
            </Link>
          </div>
          <p className="marketing-disclosure">
            Public SaaS access has not launched. Registration, collection and
            export depend on deployment, account permissions and source rights.
            No result volume, accuracy or availability is guaranteed.
          </p>
        </div>
        <div
          className="marketing-illustration"
          role="img"
          aria-label="Conceptual workspace workflow with scope, source review and job results; no live customer records"
        >
          <div className="marketing-art-heading">
            <span className="marketing-art-dot" aria-hidden="true" /> Workspace
            workflow <span className="marketing-art-label">Illustrative</span>
          </div>
          <div className="marketing-art-scope">
            <span>Search scope</span>
            <strong>United States · Canada</strong>
            <small>Development baseline</small>
          </div>
          <div className="marketing-art-flow" aria-hidden="true">
            <span>Scope</span>
            <span>→</span>
            <span>Source review</span>
            <span>→</span>
            <span>Job</span>
          </div>
          <div className="marketing-art-bottom">
            <div>
              <span>Source policy</span>
              <strong>Check eligibility</strong>
            </div>
            <div>
              <span>Results</span>
              <strong>Review before export</strong>
            </div>
          </div>
          <p className="marketing-art-caption">
            Interface concept. Not real lead data or live job results.
          </p>
        </div>
      </section>

      <section className="marketing-section" aria-labelledby="workflow-title">
        <div className="marketing-section-head">
          <p className="marketing-kicker">How it works</p>
          <h2 id="workflow-title">Three deliberate steps. No silent spend.</h2>
          <p>
            Each step leaves source eligibility and execution under user
            control.
          </p>
        </div>
        <div className="marketing-cards">
          {steps.map(([number, title, description]) => (
            <article className="marketing-card" key={number}>
              <span className="marketing-number">{number}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section
        className="marketing-section marketing-split"
        aria-labelledby="built-title"
      >
        <div>
          <p className="marketing-kicker">Implemented in development</p>
          <h2 id="built-title">Workspace-first by design.</h2>
          <p>
            The development build includes account sessions, workspace
            permission checks, drafts and submitted jobs, a bounded Overture
            source adapter, result review and guarded CSV export. Staging and
            production acceptance remain separate gates.
          </p>
          <Link href="/capabilities">See capability status →</Link>
        </div>
        <div className="marketing-feature-panel">
          <div>
            <span aria-hidden="true">✓</span>
            <strong>Workspace isolation</strong>
            <small>Server-authorized access</small>
          </div>
          <div>
            <span aria-hidden="true">✓</span>
            <strong>Job visibility</strong>
            <small>Queued and running states</small>
          </div>
          <div>
            <span aria-hidden="true">✓</span>
            <strong>Guarded exports</strong>
            <small>Current-rights and usage checks</small>
          </div>
        </div>
      </section>

      <section className="marketing-section" aria-labelledby="future-title">
        <div className="marketing-section-head">
          <p className="marketing-kicker">Roadmap · not currently offered</p>
          <h2 id="future-title">Designed to grow with your workflow.</h2>
        </div>
        <div className="marketing-cards">
          <article className="marketing-card">
            <span className="marketing-tag">Planned</span>
            <h3>Daily schedules</h3>
            <p>
              Time-zone-aware recurring jobs with explicit execution previews.
            </p>
          </article>
          <article className="marketing-card">
            <span className="marketing-tag">Planned</span>
            <h3>AI-assisted setup</h3>
            <p>
              Bounded guidance for preparing searches, with user review before
              execution.
            </p>
          </article>
          <article className="marketing-card">
            <span className="marketing-tag">Planned</span>
            <h3>Desktop and mobile</h3>
            <p>
              Additional clients after stable web, security and store
              validation.
            </p>
          </article>
        </div>
      </section>
      <section className="marketing-closing" aria-labelledby="closing-title">
        <div>
          <p className="marketing-kicker">Explore before launch</p>
          <h2 id="closing-title">
            Know what is built, planned and still gated.
          </h2>
        </div>
        <div className="marketing-actions">
          <Link className="marketing-primary" href="/plans">
            Plans and availability
          </Link>
          <Link className="marketing-secondary" href="/data-handling">
            Data handling
          </Link>
        </div>
      </section>
    </div>
  );
}
