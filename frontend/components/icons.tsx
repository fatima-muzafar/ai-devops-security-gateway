// Inline SVG icons and the logo mark (decisions.md #106). Colours come from dashboard.css.
export type IconKind = "events" | "approvals" | "services" | "logout";

export function Icon({ kind }: { kind: IconKind }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      {kind === "events" && (
        <>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
        </>
      )}
      {kind === "approvals" && (
        <>
          <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" />
          <path d="M9 12l2 2 4-4" />
        </>
      )}
      {kind === "services" && (
        <>
          <path d="M12 3l9 5-9 5-9-5z" />
          <path d="M3 12l9 5 9-5" />
          <path d="M3 16l9 5 9-5" />
        </>
      )}
      {kind === "logout" && (
        <>
          <path d="M10 4H5v16h5" />
          <path d="M15 8l4 4-4 4M19 12H9" />
        </>
      )}
    </svg>
  );
}

export function LogoMark() {
  return (
    <svg className="logo-mark" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" />
      <circle cx="12" cy="11" r="2.5" />
    </svg>
  );
}
