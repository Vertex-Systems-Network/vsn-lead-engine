import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Data handling | VSN Lead Engine",
  description: "Development-stage tenant boundaries, source rights, retention and privacy review status.",
};
const topics = [
  ["Workspace authorization", "The backend rechecks current account membership and roles for workspace-owned requests. Hiding a control is not treated as authorization."],
  ["Source-specific rights", "Publicly viewable business records are not automatically licensed for collection, resale or redistribution. Display, storage and export rights require source-specific evidence."],
  ["Lead retention and exports", "The development result flow has retention and guarded export checks. Backup, downstream deletion and production privacy operations remain uncertified."],
  ["Sessions and secrets", "Development routes use server-side sessions and CSRF checks. Credentials and sensitive account information must not enter public marketing content."],
  ["Outstanding reviews", "Provider agreements, jurisdiction-specific privacy notices, deletion commitments, subprocessors and commercial processing require separate qualified review."],
];
export default function DataHandling() {
  return (
    <div className="marketing marketing-detail">
      <section className="marketing-page-intro">
        <p className="marketing-kicker">Data handling · development overview</p>
        <h1>Source rights and access controls before volume.</h1>
        <p className="marketing-lead">This page explains current design boundaries. It is not a published legal privacy notice or a claim that the SaaS is processing live public customers.</p>
        <p className="marketing-disclosure">Privacy policy, deletion guarantees, subprocessors and jurisdictional obligations must be reviewed before launch.</p>
      </section>
      <section className="marketing-section" aria-labelledby="handling-title">
        <div className="marketing-section-head"><p className="marketing-kicker">Development boundaries</p><h2 id="handling-title">How information is intended to be handled</h2></div>
        <div className="marketing-cards">
          {topics.map(([title, description]) => (
            <article className="marketing-card" key={title}><h3>{title}</h3><p>{description}</p></article>
          ))}
        </div>
      </section>
      <section className="marketing-closing"><div><h2>Learn what is implemented and what is still planned.</h2><p>No production service or privacy certification is implied.</p></div><div className="marketing-actions"><Link className="marketing-primary" href="/capabilities">View capabilities</Link><Link className="marketing-secondary" href="/">Back to home</Link></div></section>
    </div>
  );
}
