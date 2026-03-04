"use client";

import { CheckIcon, XIcon } from "lucide-react";

export interface TradeOffOption {
  id: string;
  title: string;
  description: string;
  pros: string[];
  cons: string[];
  recommended?: boolean;
  cost_delta?: string;
}

interface Props {
  title: string;
  options: TradeOffOption[];
  onSelect: (optionId: string) => void;
  onDismiss?: () => void;
}

/**
 * TradeOffOptions — displayed by the agent when replanning with multiple viable alternatives.
 * The agent streams structured JSON in its message; the chat window can extract and render this.
 */
export default function TradeOffOptions({ title, options, onSelect, onDismiss }: Props) {
  return (
    <div className="my-3 p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-slate-800 text-sm">{title}</h3>
        {onDismiss && (
          <button onClick={onDismiss} className="text-slate-400 hover:text-slate-600">
            <XIcon className="w-4 h-4" />
          </button>
        )}
      </div>

      <div className="space-y-2">
        {options.map((option) => (
          <div
            key={option.id}
            className={`rounded-lg border p-3 cursor-pointer transition-all hover:shadow-sm ${
              option.recommended
                ? "border-primary-300 bg-primary-50"
                : "border-slate-200 hover:border-slate-300"
            }`}
            onClick={() => onSelect(option.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <p className="font-medium text-slate-800 text-sm">{option.title}</p>
                  {option.recommended && (
                    <span className="text-xs bg-primary-100 text-primary-700 px-1.5 py-0.5 rounded font-medium">
                      Recommended
                    </span>
                  )}
                  {option.cost_delta && (
                    <span className="text-xs text-slate-500">{option.cost_delta}</span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-0.5">{option.description}</p>

                <div className="mt-2 grid grid-cols-2 gap-2">
                  {option.pros.length > 0 && (
                    <ul className="space-y-0.5">
                      {option.pros.map((pro, i) => (
                        <li key={i} className="flex items-center gap-1 text-xs text-green-700">
                          <CheckIcon className="w-3 h-3 shrink-0" />
                          {pro}
                        </li>
                      ))}
                    </ul>
                  )}
                  {option.cons.length > 0 && (
                    <ul className="space-y-0.5">
                      {option.cons.map((con, i) => (
                        <li key={i} className="flex items-center gap-1 text-xs text-red-600">
                          <XIcon className="w-3 h-3 shrink-0" />
                          {con}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
              <div className="w-5 h-5 rounded-full border-2 border-slate-300 shrink-0 mt-0.5" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
