import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Capabilities | VSN Lead Engine",
  description: "What is implemented in development and what remains on the VSN Lead Engine roadmap.",
};
const implemented = [
  ["Account and workspace", "Session authentication, self-service sign-up behind an environment gate and tenant-scoped workspace permissions."],
  ["Search drafts and jobs", "Choose search scope, submit eligible manual jobs and track their state; creating a draft never dispatches work."],
  ["First source adapter", "A bounded Overture Maps Places source implementation with a verified smoke run. This is not a commercial source-rights certification."],
  ["Review and export", "Accepted records, filters and guarded CSV downloads subject to current rights, usage limits and retention rules."],
];
const roadmap = [
  ["Recurring schedules", "DST-safe contracts exist, but an operational customer scheduler is not yet verified."],
  ["Paid sources and billing", "Provider contracts, source economics, subscription prices and live payment processing are not enabled."],
  ["AI-assisted setup", "Bounded search guidance remains planned, with privacy, evaluation and spending gates."],
  ["Desktop and mobile", "Planned after stable web contracts, device testing and app-store acceptance."],
];
export default function Capabilities() {
  return (
    <div className="marketing marketing-detail">
      <section className="marketing-page-intro">
        <p className="marketing-kicker">Product capabilities</p>
        <h1>Functionality with its real development status.</h1>
        <p className="marketing-lead">Application code and live service availability are different things. Here is what has been built and what still needs implementation or review.</p>
        <p className="marketing-disclosure">The SaaS has not been publicly launched. “Implemented” means present in the development repository, not customer-certified or hosted.</p>
      </section>
      <section className="marketing-section" aria-labelledby="implemented-title">
        <div className="marketing-section-head"><p className="marketing-kicker">Built · development only</p><h2 id="implemented-title">Implemented workflows</h2></div>
        <div className="marketing-cards">
          {implemented.map(([title, description]) => (
            <article className="marketing-card" key={title}><span className="marketing-tag marketing-tag-built">Implemented in development</span><h3>{title}</h3><p>{description}</p></article>
          ))}
        </div>
      </section>
      <section className="marketing-section" aria-labelledby="planned-title">
        <div className="marketing-section-head"><p className="marketing-kicker">Not offered</p><h2 id="planned-title">Planned or awaiting external verification</h2></div>
        <div className="marketing-cards">
          {roadmap.map(([title, description]) => (
            <article className="marketing-card" key={title}><span className="marketing-tag">Planned / unverified</span><h3>{title}</h3><p>{description}</p></article>
          ))}
        </div>
      </section>
      <section className="marketing-closing"><div><h2>Review the boundaries before trying a workflow.</h2><p>Each job must satisfy current source and workspace policy.</p></div><div className="marketing-actions"><Link className="marketing-primary" href="/data-handling">Data handling</Link><Link className="marketing-secondary" href="/account/sign-in">Development sign-in</Link></div></section>
    </div>
  );
}
