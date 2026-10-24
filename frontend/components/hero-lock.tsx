// Decorative padlock (decisions.md #105). Colours come from classes in dashboard.css (#99).
export default function HeroLock() {
  return (
    <svg
      className="hero-lock"
      viewBox="0 0 420 460"
      role="img"
      aria-label="Illustration of a padlock with a shield and a check mark"
    >
      <defs>
        <linearGradient id="lockBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" className="stop-surface" />
          <stop offset="1" className="stop-bg" />
        </linearGradient>
        <linearGradient id="lockShackle" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" className="stop-accent" />
          <stop offset="1" className="stop-muted" />
        </linearGradient>
        <radialGradient id="lockHalo" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" className="stop-accent" stopOpacity="0.35" />
          <stop offset="1" className="stop-accent" stopOpacity="0" />
        </radialGradient>
        <filter id="lockGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle cx="210" cy="250" r="205" fill="url(#lockHalo)" />
      <circle className="lock-ring" cx="210" cy="250" r="150" />
      <circle className="lock-ring lock-ring-dash" cx="210" cy="250" r="185" />

      <g className="lock-circuit">
        <path d="M10 330 H80 L110 300 H140" />
        <path d="M10 200 H60 L90 230 H120" />
        <path d="M410 140 H350 L320 170 H290" />
        <path d="M410 360 H340 L310 330 H285" />
        <circle cx="140" cy="300" r="3.5" />
        <circle cx="120" cy="230" r="3.5" />
        <circle cx="290" cy="170" r="3.5" />
        <circle cx="285" cy="330" r="3.5" />
      </g>

      <path
        className="lock-shackle"
        d="M145 215 V150 A65 65 0 0 1 275 150 V215"
        stroke="url(#lockShackle)"
      />
      <path className="lock-shackle-light" d="M153 215 V150 A57 57 0 0 1 267 150 V215" />

      <rect
        className="lock-glow-outline"
        x="100"
        y="210"
        width="220"
        height="190"
        rx="28"
        filter="url(#lockGlow)"
      />
      <rect
        className="lock-body"
        x="100"
        y="210"
        width="220"
        height="190"
        rx="28"
        fill="url(#lockBody)"
      />
      <rect className="lock-plate" x="118" y="228" width="184" height="154" rx="20" />

      <path
        className="lock-shield"
        filter="url(#lockGlow)"
        d="M210 262 L250 277 V313 C250 337 232 352 210 362 C188 352 170 337 170 313 V277 Z"
      />
      <path className="lock-check" d="M192 308 L205 321 L230 292" />

      <rect className="lock-led" x="150" y="371" width="30" height="5" rx="2.5" />
      <rect className="lock-led" x="195" y="371" width="30" height="5" rx="2.5" />
      <rect className="lock-led" x="240" y="371" width="30" height="5" rx="2.5" />
    </svg>
  );
}
