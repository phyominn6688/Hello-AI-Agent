"use client";

import { useState } from "react";
import {
  UtensilsIcon, MapPinIcon, TicketIcon, BuildingIcon,
  CalendarPlusIcon, TrashIcon, ClockIcon, Loader2Icon,
} from "lucide-react";
import type { ItineraryItem, ItemType } from "@/types";

const TYPE_ICON: Record<ItemType, React.ElementType> = {
  flight: MapPinIcon,
  hotel: BuildingIcon,
  restaurant: UtensilsIcon,
  event: TicketIcon,
  activity: MapPinIcon,
  train: MapPinIcon,
  transfer: MapPinIcon,
};

interface Props {
  item: ItineraryItem;
  onSchedule: (itemId: number, date: string, startTime?: string) => Promise<void>;
  onRemove: (itemId: number) => Promise<void>;
}

export default function WishlistCard({ item, onSchedule, onRemove }: Props) {
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [schedulingDate, setSchedulingDate] = useState("");
  const [schedulingTime, setSchedulingTime] = useState("");
  const [scheduling, setScheduling] = useState(false);
  const [removing, setRemoving] = useState(false);

  const Icon = TYPE_ICON[item.type] ?? MapPinIcon;
  const city = (item.item_data as Record<string, string>)?.city || "";
  const notes = (item.item_data as Record<string, string>)?.notes || "";

  const handleSchedule = async () => {
    if (!schedulingDate) return;
    setScheduling(true);
    try {
      await onSchedule(item.id, schedulingDate, schedulingTime || undefined);
      setShowDatePicker(false);
    } finally {
      setScheduling(false);
    }
  };

  const handleRemove = async () => {
    setRemoving(true);
    try {
      await onRemove(item.id);
    } finally {
      setRemoving(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm">
      <div className="flex items-start gap-2">
        <div className="p-1 rounded-md bg-slate-50 border border-slate-100 shrink-0 mt-0.5">
          <Icon className="w-3.5 h-3.5 text-slate-500" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="font-medium text-slate-800 truncate">{item.name}</p>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
            {city && <span>{city}</span>}
            {item.duration_mins && (
              <span className="flex items-center gap-0.5">
                <ClockIcon className="w-3 h-3" />
                {item.duration_mins} min
              </span>
            )}
          </div>
          {notes && (
            <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{notes}</p>
          )}

          {showDatePicker ? (
            <div className="mt-2 space-y-1.5">
              <input
                type="date"
                value={schedulingDate}
                onChange={(e) => setSchedulingDate(e.target.value)}
                className="w-full text-xs border border-slate-200 rounded-lg px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary-500"
              />
              <input
                type="time"
                value={schedulingTime}
                onChange={(e) => setSchedulingTime(e.target.value)}
                placeholder="Time (optional)"
                className="w-full text-xs border border-slate-200 rounded-lg px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary-500"
              />
              <div className="flex gap-1.5">
                <button
                  onClick={handleSchedule}
                  disabled={!schedulingDate || scheduling}
                  className="flex-1 text-xs py-1.5 bg-primary-600 text-white rounded-lg disabled:opacity-50 flex items-center justify-center gap-1"
                >
                  {scheduling ? <Loader2Icon className="w-3 h-3 animate-spin" /> : null}
                  Add to Schedule
                </button>
                <button
                  onClick={() => setShowDatePicker(false)}
                  className="px-2 py-1.5 text-xs text-slate-600 bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-1.5 mt-2">
              <button
                onClick={() => setShowDatePicker(true)}
                className="flex items-center gap-1 px-2 py-1 text-xs text-primary-700 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors"
              >
                <CalendarPlusIcon className="w-3 h-3" />
                Schedule
              </button>
              <button
                onClick={handleRemove}
                disabled={removing}
                className="flex items-center gap-1 px-2 py-1 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-50"
              >
                {removing ? (
                  <Loader2Icon className="w-3 h-3 animate-spin" />
                ) : (
                  <TrashIcon className="w-3 h-3" />
                )}
                Remove
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
