"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon, MapPinIcon, CalendarIcon, ArrowRightIcon } from "lucide-react";
import { format } from "date-fns";
import { createTrip, listTrips } from "@/lib/api";
import { getCurrentUser, signIn } from "@/lib/auth";
import type { AuthUser } from "@/lib/auth";
import type { Trip } from "@/types";

const STATUS_BADGE: Record<string, string> = {
  planning: "bg-blue-100 text-blue-700",
  active: "bg-green-100 text-green-700",
  completed: "bg-slate-100 text-slate-600",
};

export default function TripListPage() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTripTitle, setNewTripTitle] = useState("");
  const [showNew, setShowNew] = useState(false);

  useEffect(() => {
    getCurrentUser().then((u) => {
      setUser(u);
      if (u) {
        listTrips()
          .then(setTrips)
          .catch(console.error)
          .finally(() => setLoading(false));
      } else {
        setLoading(false);
      }
    });
  }, []);

  const handleCreateTrip = async () => {
    if (!newTripTitle.trim()) return;
    setCreating(true);
    try {
      const trip = await createTrip({ title: newTripTitle.trim() });
      router.push(`/trips/${trip.id}`);
    } catch (e) {
      console.error(e);
      setCreating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen gap-6 px-4">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-slate-800 mb-2">Travel AI Agent</h1>
          <p className="text-slate-500 text-lg">Your AI-powered travel companion</p>
        </div>
        <button
          onClick={signIn}
          className="flex items-center gap-3 px-6 py-3 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition-colors shadow-sm"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">My Trips</h1>
          <p className="text-slate-500 text-sm mt-0.5">{user.email}</p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors text-sm"
        >
          <PlusIcon className="w-4 h-4" />
          New Trip
        </button>
      </div>

      {/* New trip input */}
      {showNew && (
        <div className="mb-6 p-4 bg-white rounded-xl border border-slate-200 shadow-sm animate-slide-up">
          <p className="text-sm font-medium text-slate-700 mb-2">Trip name</p>
          <div className="flex gap-2">
            <input
              autoFocus
              type="text"
              value={newTripTitle}
              onChange={(e) => setNewTripTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateTrip()}
              placeholder="e.g. China Spring Break 2025"
              className="flex-1 px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
            <button
              onClick={handleCreateTrip}
              disabled={creating || !newTripTitle.trim()}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg font-medium disabled:opacity-50 hover:bg-primary-700 transition-colors"
            >
              {creating ? "Creating…" : "Start"}
            </button>
            <button
              onClick={() => setShowNew(false)}
              className="px-3 py-2 text-sm text-slate-500 hover:text-slate-700"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Trip list */}
      {trips.length === 0 ? (
        <div className="text-center py-16 text-slate-400">
          <MapPinIcon className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">No trips yet</p>
          <p className="text-sm mt-1">Start a new trip and let AI plan it for you</p>
        </div>
      ) : (
        <div className="space-y-3">
          {trips.map((trip) => (
            <button
              key={trip.id}
              onClick={() => router.push(`/trips/${trip.id}`)}
              className="w-full text-left p-4 bg-white rounded-xl border border-slate-200 hover:border-primary-300 hover:shadow-sm transition-all group"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-slate-800 truncate">{trip.title}</h3>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[trip.status]}`}>
                      {trip.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-slate-500">
                    {trip.destinations.length > 0 && (
                      <span className="flex items-center gap-1">
                        <MapPinIcon className="w-3.5 h-3.5" />
                        {trip.destinations.map((d) => d.city).join(" → ")}
                      </span>
                    )}
                    {trip.start_date && (
                      <span className="flex items-center gap-1">
                        <CalendarIcon className="w-3.5 h-3.5" />
                        {format(new Date(trip.start_date), "MMM d")}
                        {trip.end_date && ` – ${format(new Date(trip.end_date), "MMM d, yyyy")}`}
                      </span>
                    )}
                  </div>
                </div>
                <ArrowRightIcon className="w-4 h-4 text-slate-400 group-hover:text-primary-500 transition-colors mt-0.5 shrink-0" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
