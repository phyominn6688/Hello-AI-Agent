"use client";

import { useEffect, useRef, useState } from "react";
import { SendIcon } from "lucide-react";
import MessageBubble from "./MessageBubble";
import type { ChatMessage, TripStatus } from "@/types";

const PLACEHOLDER: Record<TripStatus, string> = {
  planning: "Ask anything — \"What's the best area to stay in Beijing?\"",
  active: "Ask anything — \"Where's the nearest ATM?\" or \"What time should I leave?\"",
  completed: "This trip is completed.",
};

interface Props {
  messages: ChatMessage[];
  streaming: boolean;
  onSend: (text: string) => void;
  tripStatus: TripStatus;
}

export default function ChatWindow({ messages, streaming, onSend, tripStatus }: Props) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming || tripStatus === "completed") return;
    setInput("");
    onSend(text);
    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize textarea
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto chat-scroll px-4 py-4 space-y-1">
        {isEmpty && !streaming && (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 bg-primary-100 rounded-2xl flex items-center justify-center mb-4">
              <span className="text-3xl">✈️</span>
            </div>
            <h2 className="font-semibold text-slate-700 text-lg mb-1">
              {tripStatus === "active" ? "Good morning, traveler!" : "Start planning your trip"}
            </h2>
            <p className="text-slate-500 text-sm max-w-xs">
              {tripStatus === "active"
                ? "Ask me anything about your day — directions, restaurants, what to see next."
                : "Tell me about your dream trip. I'll handle the research, visa checks, and itinerary."}
            </p>
            {tripStatus === "planning" && (
              <div className="mt-4 grid grid-cols-1 gap-2 w-full max-w-sm">
                {[
                  "I want to take my family to China for Spring break, 10 days, $5k per person",
                  "Plan a 2-week Japan trip for 2 adults and 1 child, cherry blossom season",
                  "Weekend in Barcelona — food, architecture, no kids",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => onSend(suggestion)}
                    className="text-left px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm text-slate-600 hover:border-primary-300 hover:text-slate-800 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble
            key={i}
            message={msg}
            isStreaming={streaming && i === messages.length - 1 && msg.role === "assistant"}
            onSend={onSend}
          />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-slate-200 bg-white px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={streaming || tripStatus === "completed"}
            placeholder={PLACEHOLDER[tripStatus]}
            rows={1}
            className="flex-1 resize-none px-3 py-2.5 text-sm border border-slate-200 rounded-xl outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed max-h-40"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || streaming || tripStatus === "completed"}
            className="p-2.5 bg-primary-600 text-white rounded-xl disabled:opacity-40 hover:bg-primary-700 transition-colors shrink-0"
          >
            <SendIcon className="w-4 h-4" />
          </button>
        </div>
        {streaming && (
          <p className="text-xs text-slate-400 mt-1.5 flex items-center gap-1">
            <span className="inline-flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 bg-primary-400 rounded-full animate-pulse-dot"
                  style={{ animationDelay: `${i * 0.16}s` }}
                />
              ))}
            </span>
            Agent is thinking…
          </p>
        )}
      </div>
    </div>
  );
}
