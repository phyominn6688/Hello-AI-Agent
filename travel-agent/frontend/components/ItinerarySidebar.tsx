"use client";

import { format, parseISO } from "date-fns";
import { useEffect, useState } from "react";
import {
  PlaneTakeoffIcon, BuildingIcon, UtensilsIcon, TicketIcon,
  MapPinIcon, TrainIcon, CarIcon, CheckCircleIcon, ClockIcon,
  BookmarkIcon, ChevronDownIcon, ChevronRightIcon,
} from "lucide-react";
import type { ItineraryDay, ItineraryItem, ItemType, Trip, WishlistStatus } from "@/types";
import { getWishlist, promoteWishlistItem, removeWishlistItem } from "@/lib/api";
import WishlistCard from "./WishlistCard";

const TYPE_ICON: Record<ItemType, React.ElementType> = {
  flight: PlaneTakeoffIcon,
  hotel: BuildingIcon,
  restaurant: UtensilsIcon,
  event: TicketIcon,
  activity: MapPinIcon,
  train: TrainIcon,
  transfer: CarIcon,
};

const STATUS_STYLE: Record<WishlistStatus, string> = {
  wishlist: "border-slate-200 bg-white",
  available: "border-blue-200 bg-blue-50",
  booked: "border-green-200 bg-green-50",
  unavailable: "border-red-100 bg-red-50 opacity-60",
  replaced: "border-amber-200 bg-amber-50",
};

const STATUS_DOT: Record<WishlistStatus, string> = {
  wishlist: "bg-slate-300",
  available: "bg-blue-400",
  booked: "bg-green-500",
  unavailable: "bg-red-400",
  replaced: "bg-amber-400",
};

function ItemCard({ item }: { item: ItineraryItem }) {
  const Icon = TYPE_ICON[item.type] ?? MapPinIcon;

  return (
    <div className={`rounded-lg border px-3 py-2.5 text-sm ${STATUS_STYLE[item.wishlist_status]}`}>
      <div className="flex items-start gap-2">
        <div className="p-1 rounded-md bg-white border border-slate-100 shrink-0 mt-0.5">
          <Icon className="w-3.5 h-3.5 text-slate-600" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${STATUS_DOT[item.wishlist_status]}`} />
            <p className="font-medium text-slate-800 truncate">{item.name}</p>
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
            {item.start_time && (
              <span className="flex items-center gap-0.5">
                <ClockIcon className="w-3 h-3" />
                {item.start_time.slice(0, 5)}
                {item.end_time && ` – ${item.end_time.slice(0, 5)}`}
              </span>
            )}
            {item.flexibility === "fixed" && (
              <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-600 font-medium">
                fixed
              </span>
            )}
            {item.booking_ref && (
              <span className="flex items-center gap-0.5 text-green-700">
                <CheckCircleIcon className="w-3 h-3" />
                {item.booking_ref}
              </span>
            )}
          </div>
          {item.location?.address && (
            <p className="text-xs text-slate-400 mt-0.5 truncate">{item.location.address}</p>
          )}
          {item.wallet_pass_url && (
            <div className="flex gap-2 mt-1.5">
              {item.wallet_pass_url.apple && (
                <a
                  href={item.wallet_pass_url.apple}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-slate-700 bg-slate-900 text-white px-2 py-0.5 rounded hover:bg-slate-700 transition-colors"
                >
                  <BookmarkIcon className="w-3 h-3" />
                  Apple Wallet
                </a>
              )}
              {item.wallet_pass_url.google && (
                <a
                  href={item.wallet_pass_url.google}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-white bg-blue-600 px-2 py-0.5 rounded hover:bg-blue-700 transition-colors"
                >
                  <BookmarkIcon className="w-3 h-3" />
                  Google Wallet
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DaySection({ day }: { day: ItineraryDay }) {
  const date = parseISO(day.date);
  const sortedItems = [...day.items].sort((a, b) => {
    if (!a.start_time) return 1;
    if (!b.start_time) return -1;
    return a.start_time.localeCompare(b.start_time);
  });

  return (
    <div className="mb-5">
      <div className="px-4 py-2 bg-slate-50 border-b border-t border-slate-100 sticky top-0">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
          {format(date, "EEEE, MMM d")}
        </p>
      </div>
      <div className="px-4 py-3 space-y-2">
        {sortedItems.length === 0 ? (
          <p className="text-xs text-slate-400 italic">No items yet — ask the agent to add some</p>
        ) : (
          sortedItems.map((item) => <ItemCard key={item.id} item={item} />)
        )}
      </div>
    </div>
  );
}

interface Props {
  trip: Trip;
  itinerary: ItineraryDay[];
}

export default function ItinerarySidebar({ trip, itinerary }: Props) {
  const sortedDays = [...itinerary].sort((a, b) => a.date.localeCompare(b.date));
  const [wishlistOpen, setWishlistOpen] = useState(false);
  const [wishlistItems, setWishlistItems] = useState<ItineraryItem[]>([]);

  useEffect(() => {
    if (!wishlistOpen) return;
    getWishlist(trip.id)
      .then(setWishlistItems)
      .catch(() => {});
  }, [wishlistOpen, trip.id]);

  const handleSchedule = async (itemId: number, date: string, startTime?: string) => {
    await promoteWishlistItem(trip.id, itemId, date, startTime);
    setWishlistItems((prev) => prev.filter((i) => i.id !== itemId));
  };

  const handleRemove = async (itemId: number) => {
    await removeWishlistItem(trip.id, itemId);
    setWishlistItems((prev) => prev.filter((i) => i.id !== itemId));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-slate-100">
        <h2 className="font-semibold text-slate-800 text-sm">Your Itinerary</h2>
        {trip.destinations.length > 0 && (
          <p className="text-xs text-slate-500 mt-0.5">
            {trip.destinations.map((d) => d.city).join(" → ")}
          </p>
        )}
        {trip.start_date && trip.end_date && (
          <p className="text-xs text-slate-400">
            {format(parseISO(trip.start_date), "MMM d")} –{" "}
            {format(parseISO(trip.end_date), "MMM d, yyyy")}
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {sortedDays.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-slate-400">
              Your itinerary will appear here as you plan with the agent.
            </p>
          </div>
        ) : (
          sortedDays.map((day) => <DaySection key={day.id} day={day} />)
        )}

        {/* Wishlist collapsible section */}
        <div className="border-t border-slate-100">
          <button
            onClick={() => setWishlistOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold text-slate-500 uppercase tracking-wide hover:bg-slate-50 transition-colors"
          >
            <span>Wishlist</span>
            {wishlistOpen ? (
              <ChevronDownIcon className="w-3.5 h-3.5" />
            ) : (
              <ChevronRightIcon className="w-3.5 h-3.5" />
            )}
          </button>
          {wishlistOpen && (
            <div className="px-4 pb-4 space-y-2">
              {wishlistItems.length === 0 ? (
                <p className="text-xs text-slate-400 italic">
                  No wishlist items yet — tell the agent to save something for later.
                </p>
              ) : (
                wishlistItems.map((item) => (
                  <WishlistCard
                    key={item.id}
                    item={item}
                    onSchedule={handleSchedule}
                    onRemove={handleRemove}
                  />
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Budget summary */}
      {trip.budget_per_person && (
        <div className="px-4 py-3 border-t border-slate-100 bg-slate-50">
          <p className="text-xs text-slate-500">
            Budget:{" "}
            <span className="font-semibold text-slate-700">
              {trip.budget_per_person.toLocaleString()} {trip.currency} / person
            </span>
          </p>
        </div>
      )}
    </div>
  );
}
