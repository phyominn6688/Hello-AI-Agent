import { useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import type { Trip } from "../types";
import { createTrip, listTrips } from "../lib/api";
import { signOut } from "../lib/auth";

interface Props {
  onOpenTrip: (tripId: number) => void;
  onSignOut: () => void;
}

export default function TripList({ onOpenTrip, onSignOut }: Props) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listTrips()
      .then(setTrips)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = async () => {
    const title = newTitle.trim();
    if (!title) return;
    setCreating(true);
    try {
      const trip = await createTrip({ title });
      setTrips((prev) => [trip, ...prev]);
      setShowCreate(false);
      setNewTitle("");
      onOpenTrip(trip.id);
    } catch (err) {
      console.error("Create trip failed:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleSignOut = async () => {
    await signOut();
    onSignOut();
  };

  const formatDates = (trip: Trip) => {
    if (trip.start_date && trip.end_date) {
      return `${format(parseISO(trip.start_date), "MMM d")} – ${format(parseISO(trip.end_date), "MMM d, yyyy")}`;
    }
    return "Dates not set";
  };

  return (
    <div className="trips-screen">
      <div className="trips-header">
        <h1>My Trips</h1>
        <button className="btn-icon" onClick={handleSignOut} title="Sign out">
          👤
        </button>
      </div>

      <div className="trips-list">
        {loading && (
          <div className="trips-empty">
            <div className="trips-empty-icon">⏳</div>
            <p>Loading trips…</p>
          </div>
        )}

        {!loading && trips.length === 0 && (
          <div className="trips-empty">
            <div className="trips-empty-icon">🗺️</div>
            <p>No trips yet. Tap + to plan your first adventure.</p>
          </div>
        )}

        {trips.map((trip) => (
          <button
            key={trip.id}
            className="trip-card"
            onClick={() => onOpenTrip(trip.id)}
          >
            <div className="trip-card-title">{trip.title}</div>
            <div className="trip-card-meta">
              {trip.destinations.length > 0
                ? trip.destinations.map((d) => d.city).join(" → ")
                : "Destination TBD"}
            </div>
            <div className="trip-card-meta">{formatDates(trip)}</div>
            <span className={`trip-card-status status-${trip.status}`}>
              {trip.status}
            </span>
          </button>
        ))}
      </div>

      <button className="fab" onClick={() => setShowCreate(true)}>
        +
      </button>

      {showCreate && (
        <div className="modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="modal-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="modal-title">New Trip</div>
            <input
              className="input-field"
              type="text"
              placeholder="Trip name (e.g. Japan Spring 2026)"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <button
              className="btn-primary"
              onClick={handleCreate}
              disabled={creating || !newTitle.trim()}
            >
              {creating ? "Creating…" : "Create Trip"}
            </button>
            <button className="btn-cancel" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
