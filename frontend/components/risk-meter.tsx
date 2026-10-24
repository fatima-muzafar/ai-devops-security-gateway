// Risk LEVEL bar (decisions.md #106): 12 ticks, LOW 4 / MEDIUM 8 / HIGH 12. Not a measured score.
// The text label is always shown, so colour is never the only signal.
import { riskDetailText } from "@/lib/format";
import type { Risk, RiskLevel } from "@/lib/types";

const TICKS = 12;
const FILLED: Record<RiskLevel, number> = { LOW: 4, MEDIUM: 8, HIGH: 12 };

export default function RiskMeter({ risk }: { risk: Risk | null }) {
  if (!risk) return <span className="muted">none</span>;
  const filled = FILLED[risk.final_risk_level] ?? 0;
  return (
    <span className="risk">
      <span className="risk-label">{risk.final_risk_level}</span>
      <span className="risk-bar" aria-hidden="true">
        {Array.from({ length: TICKS }, (_, i) => {
          const zone = i < 4 ? "lo" : i < 8 ? "mid" : "hi";
          return <span key={i} className={i < filled ? `tick tick-on tick-${zone}` : "tick"} />;
        })}
      </span>
      <span className="risk-detail">{riskDetailText(risk)}</span>
    </span>
  );
}
