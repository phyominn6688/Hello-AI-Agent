import type { Alert } from "../types";

interface Props {
  alert: Alert;
  onDismiss: () => void;
}

export default function AlertBanner({ alert, onDismiss }: Props) {
  const icon = alertIcon(alert.type);

  return (
    <div className="alert-banner" role="alert">
      <span>{icon}</span>
      <span className="alert-message">{alert.message}</span>
      <button className="btn-dismiss" onClick={onDismiss} aria-label="Dismiss">
        ✕
      </button>
    </div>
  );
}

function alertIcon(type: string): string {
  switch (type) {
    case "flight_change": return "✈";
    case "cancellation": return "❌";
    case "weather": return "🌦";
    case "reminder": return "⏰";
    case "leave_now": return "🏃";
    default: return "ℹ";
  }
}
