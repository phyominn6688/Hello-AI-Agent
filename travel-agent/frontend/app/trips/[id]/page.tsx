"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon } from "lucide-react";
import {
  getConversation,
  getItinerary,
  getTrip,
  postLocation,
  streamChat,
} from "@/lib/api";
import type { ChatMessage, ItineraryDay, Trip } from "@/types";
import ChatWindow from "@/components/ChatWindow";
import ItinerarySidebar from "@/components/ItinerarySidebar";
import AlertBanner from "@/components/AlertBanner";
import DayBriefing from "@/components/DayBriefing";

export default function TripPage() {
  const { id } = useParams<{ id: string }>();
  const tripId = Number(id);

  const [trip, setTrip] = useState<Trip | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [itinerary, setItinerary] = useState<ItineraryDay[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  // Load trip + conversation on mount
  useEffect(() => {
    if (!tripId) return;
    Promise.all([
      getTrip(tripId),
      getConversation(tripId),
      getItinerary(tripId),
    ])
      .then(([t, conv, itin]) => {
        setTrip(t);
        setMessages(conv.messages);
        setItinerary(itin);
      })
      .catch(console.error);
  }, [tripId]);

  // Geolocation — only for active trips
  useEffect(() => {
    if (trip?.status !== "active") return;
    if (!navigator.geolocation) return;

    const postLoc = (pos: GeolocationPosition) => {
      postLocation(tripId, pos.coords.latitude, pos.coords.longitude).catch(() => {});
    };

    navigator.geolocation.getCurrentPosition(postLoc, () => {});

    const interval = setInterval(() => {
      navigator.geolocation.getCurrentPosition(postLoc, () => {});
    }, 5 * 60 * 1000); // every 5 minutes

    return () => clearInterval(interval);
  }, [trip?.status, tripId]);

  const handleSend = async (text: string) => {
    if (streaming || !text.trim()) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    let assistantContent = "";
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", timestamp: new Date().toISOString() },
    ]);

    try {
      for await (const event of streamChat(tripId, text)) {
        if (event.type === "text") {
          assistantContent += event.content;
          setMessages((prev) => {
            const updated = [...prev];
            const lastIdx = updated.length - 1;
            if (updated[lastIdx]?.role === "assistant") {
              updated[lastIdx] = { ...updated[lastIdx], content: assistantContent };
            }
            return updated;
          });
        } else if (event.type === "done") {
          // Refresh itinerary in case agent added/booked items
          getItinerary(tripId).then(setItinerary).catch(console.error);
        }
        // booking_intent, booking_started, booking_complete are handled by ChatWindow
      }
    } catch (e) {
      console.error("Stream error:", e);
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (updated[lastIdx]?.role === "assistant" && !updated[lastIdx].content) {
          updated[lastIdx] = {
            ...updated[lastIdx],
            content: "Sorry, something went wrong. Please try again.",
          };
        }
        return updated;
      });
    } finally {
      setStreaming(false);
    }
  };

  if (!trip) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const todayStr = new Date().toISOString().slice(0, 10);
  const todayItinerary = itinerary.find((d) => d.date === todayStr) ?? null;

  return (
    <div className="flex flex-col h-screen bg-surface">
      {/* Top nav */}
      <header className="flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 shrink-0">
        <Link
          href="/"
          className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <ArrowLeftIcon className="w-4 h-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <h1 className="font-semibold text-slate-800 truncate">{trip.title}</h1>
          <p className="text-xs text-slate-500 capitalize">{trip.status} mode</p>
        </div>
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="px-3 py-1.5 text-xs font-medium text-slate-600 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
        >
          {sidebarOpen ? "Hide Plan" : "View Plan"}
        </button>
      </header>

      {/* Alerts */}
      <AlertBanner tripId={tripId} />

      {/* Day briefing — guide mode only */}
      {trip.status === "active" && todayItinerary && (
        <div className="px-4 py-3 border-b border-slate-200 bg-white shrink-0">
          <DayBriefing day={todayItinerary} />
        </div>
      )}

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat */}
        <main className="flex-1 flex flex-col min-w-0">
          <ChatWindow
            messages={messages}
            streaming={streaming}
            onSend={handleSend}
            tripStatus={trip.status}
          />
        </main>

        {/* Itinerary sidebar — collapsible */}
        {sidebarOpen && (
          <aside className="w-80 shrink-0 border-l border-slate-200 bg-white overflow-y-auto hidden md:block">
            <ItinerarySidebar trip={trip} itinerary={itinerary} />
          </aside>
        )}
      </div>
    </div>
  );
}
