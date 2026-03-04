"use client";

import { useEffect, useState } from "react";
import { XIcon, AlertTriangleIcon, InfoIcon, BellIcon } from "lucide-react";
import { getAlerts, markAlertRead } from "@/lib/api";
import type { Alert } from "@/types";

const ALERT_STYLE: Record<string, string> = {
  flight_change: "bg-red-50 border-red-200 text-red-800",
  cancellation: "bg-red-50 border-red-200 text-red-800",
  weather: "bg-amber-50 border-amber-200 text-amber-800",
  reminder: "bg-blue-50 border-blue-200 text-blue-800",
  leave_now: "bg-green-50 border-green-200 text-green-800",
  default: "bg-slate-50 border-slate-200 text-slate-800",
};

const ALERT_ICON: Record<string, React.ElementType> = {
  flight_change: AlertTriangleIcon,
  cancellation: AlertTriangleIcon,
  weather: AlertTriangleIcon,
  leave_now: BellIcon,
  default: InfoIcon,
};

interface Props {
  tripId: number;
}

export default function AlertBanner({ tripId }: Props) {
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    getAlerts(tripId)
      .then((all) => setAlerts(all.filter((a) => !a.read_at)))
      .catch(() => {});

    // Poll every 30s for new alerts (Iteration 2: replace with WebSocket/SSE push)
    const interval = setInterval(() => {
      getAlerts(tripId)
        .then((all) => setAlerts(all.filter((a) => !a.read_at)))
        .catch(() => {});
    }, 30_000);

    return () => clearInterval(interval);
  }, [tripId]);

  const dismiss = async (alertId: number) => {
    setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    try {
      await markAlertRead(tripId, alertId);
    } catch {}
  };

  if (alerts.length === 0) return null;

  return (
    <div className="px-4 py-2 space-y-2 border-b border-slate-200 bg-white">
      {alerts.slice(0, 3).map((alert) => {
        const style = ALERT_STYLE[alert.type] ?? ALERT_STYLE.default;
        const Icon = ALERT_ICON[alert.type] ?? ALERT_ICON.default;
        return (
          <div
            key={alert.id}
            className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-sm ${style} animate-slide-up`}
          >
            <Icon className="w-4 h-4 shrink-0 mt-0.5" />
            <p className="flex-1">{alert.message}</p>
            <button
              onClick={() => dismiss(alert.id)}
              className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
            >
              <XIcon className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
