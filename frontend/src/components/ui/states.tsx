import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  sub,
  action,
}: {
  eyebrow: string;
  title: string;
  sub?: string;
  action?: ReactNode;
}) {
  return (
    <div className={action ? "dash-page-header dash-page-header-row" : "dash-page-header"}>
      <div>
        <p className="dash-eyebrow">{eyebrow}</p>
        <h1 className="dash-section-title">{title}</h1>
        {sub ? <p className="dash-page-sub">{sub}</p> : null}
      </div>
      {action}
    </div>
  );
}

export type EmptyIcon = "panel" | "drone" | "wrench" | "droplet" | "map" | "report" | "gear" | "chart";

const ICONS: Record<EmptyIcon, ReactNode> = {
  panel: (
    <>
      <rect x="6" y="14" width="52" height="30" />
      <path d="M6 24h52M6 34h52M19 14v30M32 14v30M45 14v30M32 44v8M22 52h20" />
    </>
  ),
  drone: (
    <>
      <rect x="25" y="26" width="14" height="8" />
      <path d="M25 30H12M39 30h13M12 24v12M52 24v12M6 24h12M46 24h12M32 34v8" />
      <circle cx="32" cy="46" r="3" />
    </>
  ),
  wrench: <path d="M40 10a12 12 0 0 0-11 16L10 45l9 9 19-19a12 12 0 0 0 16-11l-8 8-7-2-2-7z" />,
  droplet: (
    <>
      <path d="M32 8C22 22 16 30 16 38a16 16 0 0 0 32 0c0-8-6-16-16-30z" />
      <path d="M24 40a8 8 0 0 0 8 8" />
    </>
  ),
  map: (
    <>
      <path d="M8 14l16-6 16 6 16-6v42l-16 6-16-6-16 6z" />
      <path d="M24 8v42M40 14v42" />
    </>
  ),
  report: (
    <>
      <path d="M16 6h22l10 10v42H16z" />
      <path d="M38 6v10h10M22 28h20M22 36h20M22 44h12" />
    </>
  ),
  gear: (
    <>
      <circle cx="32" cy="32" r="9" />
      <path d="M32 6v10M32 48v10M6 32h10M48 32h10M14 14l7 7M43 43l7 7M50 14l-7 7M21 43l-7 7" />
    </>
  ),
  chart: (
    <>
      <path d="M8 8v48h48" />
      <path d="M14 44l12-14 10 8 16-22" />
    </>
  ),
};

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: EmptyIcon;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="sd-empty dash-card">
      <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden="true" strokeLinecap="square">
        {ICONS[icon]}
      </svg>
      <p className="sd-empty-title">{title}</p>
      <p>{children}</p>
      {action ? <div style={{ marginTop: "1rem" }}>{action}</div> : null}
    </div>
  );
}

export function LoadingState({ label = "Loading…", rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="dash-loading" role="status" aria-live="polite">
      <div className="dash-spinner" />
      <div>{label}</div>
      <div style={{ width: "min(32rem, 100%)", marginTop: "1rem" }} aria-hidden="true">
        {Array.from({ length: rows }, (_, i) => (
          <span key={i} className="sd-skeleton" style={{ width: `${100 - i * 9}%` }} />
        ))}
      </div>
    </div>
  );
}
