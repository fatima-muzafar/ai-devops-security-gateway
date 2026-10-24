import { Fragment } from "react";
import HeroLock from "./hero-lock";

// Landing view (decisions.md #105). Every sentence here must stay true to what is built.

interface Props {
  onGetStarted: () => void;
}

const CARDS = [
  {
    icon: "shield",
    title: "Every request is checked",
    text: "Authentication, validation, service ownership and role policy run before any tool is called.",
  },
  {
    icon: "pause",
    title: "Risky actions wait for a human",
    text: "Risky production changes need an admin approval, and the request is revalidated right before it runs.",
  },
  {
    icon: "list",
    title: "Everything leaves evidence",
    text: "Each request and decision is recorded under one request ID, and this dashboard shows the state of the simulated services.",
  },
];

const FLOW = [
  { name: "Developer", note: "asks in plain language", main: false },
  { name: "AI agent", note: "proposes one tool request", main: false },
  { name: "Security Gateway", note: "checks, decides, records", main: true },
  { name: "DevOps tools", note: "run only after permission", main: false },
  { name: "Simulated environment", note: "no real infrastructure", main: false },
];

function CardIcon({ kind }: { kind: string }) {
  return (
    <svg className="card-icon" viewBox="0 0 24 24" aria-hidden="true">
      {kind === "shield" && (
        <>
          <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" />
          <path d="M9 12l2 2 4-4" />
        </>
      )}
      {kind === "pause" && (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M10 9v6M14 9v6" />
        </>
      )}
      {kind === "list" && (
        <>
          <rect x="4" y="3" width="16" height="18" rx="2" />
          <path d="M8 8h8M8 12h8M8 16h5" />
        </>
      )}
    </svg>
  );
}

export default function Hero({ onGetStarted }: Props) {
  return (
    <div className="hero">
      <header className="hero-nav">
        <span className="hero-brand">Security Gateway</span>
        <nav className="hero-links">
          <a href="#features">Protection</a>
          <a href="#how">How it works</a>
        </nav>
        <button className="button hero-login" type="button" onClick={onGetStarted}>
          Log in
        </button>
      </header>

      <section className="hero-main">
        <div className="hero-copy">
          <span className="hero-tag">Final year project &middot; Sandbox only</span>
          <h1 className="hero-title">
            Your AI agent proposes.
            <br />
            <span className="hero-title-accent">The Gateway decides.</span>
          </h1>
          <p className="hero-sub">
            Authentication, risk checks and human approval stand between an autonomous DevOps
            agent and the tools it can run.
          </p>
          <div className="hero-actions">
            <button className="button button-primary hero-cta" type="button" onClick={onGetStarted}>
              Get Started
            </button>
            <a className="hero-more" href="#how">
              Learn more &rarr;
            </a>
          </div>
          <ul className="hero-stats">
            <li>
              <strong>5</strong>
              <span>DevOps tools</span>
            </li>
            <li>
              <strong>6</strong>
              <span>service environments</span>
            </li>
            <li>
              <strong>3</strong>
              <span>possible decisions</span>
            </li>
          </ul>
        </div>

        <div className="hero-art">
          <HeroLock />
          <span className="badge badge-allow hero-chip hero-chip-1">ALLOW</span>
          <span className="badge badge-approval hero-chip hero-chip-2">APPROVAL_REQUIRED</span>
          <span className="badge badge-block hero-chip hero-chip-3">BLOCK</span>
        </div>
      </section>

      <section className="hero-section" id="features">
        <h2 className="hero-heading">Control before execution</h2>
        <p className="hero-lead">The agent never touches the tools directly.</p>
        <div className="hero-cards">
          {CARDS.map((card) => (
            <article className="hero-card" key={card.title}>
              <CardIcon kind={card.icon} />
              <h3>{card.title}</h3>
              <p>{card.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="hero-section" id="how">
        <h2 className="hero-heading">How it works</h2>
        <p className="hero-lead">One mandatory path for every tool request.</p>
        <div className="flow">
          {FLOW.map((node, i) => (
            <Fragment key={node.name}>
              <div className={node.main ? "flow-node flow-node-main" : "flow-node"}>
                <strong>{node.name}</strong>
                <span>{node.note}</span>
              </div>
              {i < FLOW.length - 1 && <span className="flow-arrow" aria-hidden="true" />}
            </Fragment>
          ))}
        </div>
        <p className="flow-caption">
          Only an ALLOW, or a request that an admin approved and that passed revalidation, reaches
          the tools.
        </p>
        <ul className="flow-outcomes">
          <li>
            <span className="badge badge-allow">ALLOW</span> all checks pass and the risk is low
          </li>
          <li>
            <span className="badge badge-block">BLOCK</span> a hard check fails, nothing runs
          </li>
          <li>
            <span className="badge badge-approval">APPROVAL_REQUIRED</span> waits for an admin
          </li>
        </ul>
      </section>

      <footer className="hero-foot">
        Sandbox only: every action runs against a simulated environment. No real infrastructure is
        connected.
      </footer>
    </div>
  );
}
