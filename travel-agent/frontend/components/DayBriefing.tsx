"use client";

import { format, parseISO } from "date-fns";
import { SunIcon, CloudRainIcon, ThermometerIcon, ClockIcon } from "lucide-react";
import type { ItineraryDay, ItineraryItem } from "@/types";

interface WeatherSummary {
  temp: string;
  description: string;
  icon?: string;
}

interface Props {
  day: ItineraryDay;
  weather?: WeatherSummary;
}

export default function DayBriefing({ day, weather }: Props) {
  const date = parseISO(day.date);
  const fixedItems = day.items.filter((i) => i.flexibility === "fixed");
  const nextFixed = fixedItems.sort((a, b) =>
    (a.start_time ?? "").localeCompare(b.start_time ?? "")
  )[0];

  return (
    <div className="bg-gradient-to-br from-primary-600 to-primary-700 rounded-2xl p-4 text-white shadow-lg">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-primary-200 text-xs font-medium uppercase tracking-wide">
            Today's Briefing
          </p>
          <h2 className="font-bold text-lg">{format(date, "EEEE, MMMM d")}</h2>
        </div>
        {weather && (
          <div className="text-right">
            <p className="font-semibold">{weather.temp}</p>
            <p className="text-xs text-primary-200 capitalize">{weather.description}</p>
          </div>
        )}
      </div>

      {day.items.length === 0 ? (
        <p className="text-primary-200 text-sm">No items scheduled. Ask the agent what to do today!</p>
      ) : (
        <div className="space-y-1.5">
          {day.items
            .sort((a, b) => (a.start_time ?? "").localeCompare(b.start_time ?? ""))
            .slice(0, 4)
            .map((item) => (
              <div key={item.id} className="flex items-center gap-2 text-sm">
                <span className="text-primary-300 text-xs w-10 shrink-0">
                  {item.start_time?.slice(0, 5) ?? "–"}
                </span>
                <span
                  className={`flex-1 truncate ${
                    item.flexibility === "fixed" ? "font-medium" : "text-primary-100"
                  }`}
                >
                  {item.name}
                </span>
                {item.flexibility === "fixed" && (
                  <span className="text-xs bg-white/20 px-1.5 py-0.5 rounded">fixed</span>
                )}
              </div>
            ))}
          {day.items.length > 4 && (
            <p className="text-primary-300 text-xs">+{day.items.length - 4} more items</p>
          )}
        </div>
      )}

      {nextFixed && (
        <div className="mt-3 pt-3 border-t border-white/20">
          <p className="text-xs text-primary-200 flex items-center gap-1">
            <ClockIcon className="w-3 h-3" />
            Next fixed: <span className="font-medium text-white ml-1">{nextFixed.name}</span>
            <span className="text-primary-300">@ {nextFixed.start_time?.slice(0, 5)}</span>
          </p>
        </div>
      )}
    </div>
  );
}
