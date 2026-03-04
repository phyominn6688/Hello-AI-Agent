import { useEffect, useRef, useState } from "react";
import { format, parseISO } from "date-fns";
import type { ItineraryDay, ItineraryItem, WishlistStatus } from "../types";

interface Props {
  itinerary: ItineraryDay[];
  onClose: () => void;
}

export default function ItinerarySheet({ itinerary, onClose }: Props) {
  const [closing, setClosing] = useState(false);
  const touchStartY = useRef<number | null>(null);

  const dismiss = () => {
    setClosing(true);
    setTimeout(onClose, 260); // match CSS transition duration
  };

  const onTouchStart = (e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY;
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartY.current === null) return;
    const delta = e.changedTouches[0].clientY - touchStartY.current;
    if (delta > 60) dismiss();
    touchStartY.current = null;
  };

  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const sorted = [...itinerary].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  return (
    <>
      <div
        className={`sheet-backdrop${closing ? " closing" : ""}`}
        onClick={dismiss}
      />
      <div
        className={`itinerary-sheet${closing ? " closing" : ""}`}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
      >
        <div className="sheet-handle-bar" />
        <div className="sheet-header">
          <span className="sheet-title">Itinerary</span>
          <button className="btn-icon" onClick={dismiss}>✕</button>
        </div>
        <div className="sheet-body">
          {sorted.length === 0 ? (
            <div className="sheet-empty">
              No itinerary yet. Start planning in chat!
            </div>
          ) : (
            sorted.map((day) => (
              <DaySection key={day.id} day={day} />
            ))
          )}
        </div>
      </div>
    </>
  );
}

function DaySection({ day }: { day: ItineraryDay }) {
  const sorted = [...day.items].sort((a, b) => {
    if (!a.start_time) return 1;
    if (!b.start_time) return -1;
    return a.start_time.localeCompare(b.start_time);
  });

  return (
    <div className="sheet-day">
      <div className="sheet-day-header">
        {format(parseISO(day.date), "EEE, MMM d")}
      </div>
      {sorted.map((item) => (
        <ItemRow key={item.id} item={item} />
      ))}
    </div>
  );
}

function ItemRow({ item }: { item: ItineraryItem }) {
  return (
    <div className="sheet-item">
      <div
        className="sheet-item-dot"
        style={{ background: statusColor(item.wishlist_status) }}
      />
      <div className="sheet-item-content">
        <div className="sheet-item-name">{item.name}</div>
        <div className="sheet-item-meta">
          {itemMeta(item)}
        </div>
      </div>
    </div>
  );
}

function itemMeta(item: ItineraryItem): string {
  const parts: string[] = [];
  if (item.start_time) {
    parts.push(formatTime(item.start_time));
    if (item.end_time) parts.push(`– ${formatTime(item.end_time)}`);
  }
  if (item.location?.address) parts.push(item.location.address);
  return parts.join(" ") || typeLabel(item.type);
}

function formatTime(t: string): string {
  // t may be "HH:MM:SS" or ISO datetime
  const date = t.includes("T") ? new Date(t) : new Date(`2000-01-01T${t}`);
  return format(date, "h:mm a");
}

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    flight: "✈ Flight",
    hotel: "🏨 Hotel",
    restaurant: "🍽 Restaurant",
    event: "🎟 Event",
    activity: "🎯 Activity",
    train: "🚄 Train",
    transfer: "🚗 Transfer",
  };
  return map[type] ?? type;
}

function statusColor(status: WishlistStatus): string {
  const map: Record<WishlistStatus, string> = {
    wishlist: "var(--color-wishlist-wishlist)",
    available: "var(--color-wishlist-available)",
    booked: "var(--color-wishlist-booked)",
    unavailable: "var(--color-wishlist-unavailable)",
    replaced: "var(--color-wishlist-replaced)",
  };
  return map[status];
}
