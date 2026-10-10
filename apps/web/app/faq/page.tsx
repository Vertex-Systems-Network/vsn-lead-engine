import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Frequently asked questions | VSN Lead Engine",
  description:
    "Development-stage answers about lead workflows, source rights, local setup assistance, invitations and subscription availability.",
};

const questions = [
  {
    question: "Can customers use the SaaS service today?",
    answer:
      "No public customer launch has been approved. Development routes, unit tests and local HTTP smoke checks do not establish hosted availability, operating guarantees or an accepted production release.",
  },
  {
    question: "Which business markets and lead sources are available?",
    answer:
      "The current development search scope targets the United States and Canada. A bounded Overture Maps Places adapter has been tested, but specific collection, retention and redistribution rights, source eligibility and production availability must be separately verified.",
  },
  {
    question: "Does saving a draft start collecting leads?",
    answer:
      "No. A saved draft records requested preferences only. Eligible manual submissions require current authorization, quota and verified source policy; collection requires an enabled execution worker. Requested lead counts are not a delivery guarantee.",
  },
  {
    question: "Does the search setup assistant call an AI model?",
    answer:
      "No. The current development preview uses fixed local rules and a synthetic 50-case regression set. It does not contact an LLM, purchase model tokens or save a job on preview. A human must review and explicitly save any draft. Real model-backed assistance remains gated on provider, privacy, evaluation and budget approvals.",
  },
  {
    question: "Can a workspace invite teammates?",
    answer:
      "In development, an owner or administrator can issue a short-lived, one-time code for an existing active account, with role restrictions and audit checks. Code sharing is manual; no invitation email or SMS provider is connected.",
  },
  {
    question: "Are subscriptions, plans or trials available?",
    answer:
      "No. Pricing, included credits, trials, charges and live billing are not active. Any plan labels shown on this site are unpriced product concepts, not an offer to sell access.",
  },
  {
    question: "Will the service email, text or call prospects?",
    answer:
      "Not in this development workflow. It is designed around business search, accepted-result review and guarded export. No automatic outreach or prospect-contact delivery is enabled.",
  },
];

export default function FrequentlyAskedQuestions() {
  return (
    <div className="marketing marketing-detail">
      <section className="marketing-page-intro">
        <p className="marketing-kicker">Product questions · development only</p>
        <h1>Frequently asked questions</h1>
        <p className="marketing-lead">
          Clear answers about what is implemented, what is not yet offered and
          where external verification is still required.
        </p>
        <p className="marketing-disclosure">
          This information describes a development repository, not a hosted
          customer service, contractual promise, legal privacy notice or
          independently verified source license.
        </p>
      </section>
      <section className="marketing-section" aria-labelledby="faq-title">
        <div className="marketing-section-head">
          <h2 id="faq-title">Scope, privacy and availability</h2>
          <p>
            Expand any question to read the answer. All disclosures remain
            available without JavaScript or a signed-in session.
          </p>
        </div>
        <div className="faq-list">
          {questions.map(({ question, answer }) => (
            <details key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="marketing-closing">
        <div>
          <h2>Review development capabilities and boundaries.</h2>
          <p>Public availability remains subject to separate release gates.</p>
        </div>
        <div className="marketing-actions">
          <Link className="marketing-primary" href="/capabilities">
            View capabilities
          </Link>
          <Link className="marketing-secondary" href="/data-handling">
            Data handling
          </Link>
        </div>
      </section>
    </div>
  );
}
