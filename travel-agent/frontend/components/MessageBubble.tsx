"use client";

import { useState } from "react";
import { format } from "date-fns";
import type { ChatMessage } from "@/types";
import TradeOffOptions, { type TradeOffOption } from "./TradeOffOptions";

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
  onSend?: (text: string) => void;
}

// Minimal markdown renderer — handles **bold**, *italic*, headers, lists, code
function renderMarkdown(text: string): string {
  return text
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>")
    .replace(/^---$/gm, "<hr>")
    .replace(/^[-•] (.+)$/gm, "<li>$1</li>")
    .replace(/^\d+\. (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<[hHuUoOlLpP])(.+)$/gm, "<p>$1</p>")
    .replace(/<p><\/p>/g, "");
}

// Split message content into text segments and trade_off_options blocks
type Segment =
  | { kind: "text"; content: string }
  | { kind: "trade_off"; title: string; options: TradeOffOption[] };

function parseSegments(content: string): Segment[] {
  const FENCE_RE = /```trade_off_options\n([\s\S]*?)```/g;
  const segments: Segment[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = FENCE_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ kind: "text", content: content.slice(lastIndex, match.index) });
    }
    try {
      const parsed = JSON.parse(match[1].trim());
      segments.push({
        kind: "trade_off",
        title: parsed.title ?? "Options",
        options: parsed.options ?? [],
      });
    } catch {
      // Malformed JSON — render as plain text
      segments.push({ kind: "text", content: match[0] });
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    segments.push({ kind: "text", content: content.slice(lastIndex) });
  }

  return segments.length > 0 ? segments : [{ kind: "text", content }];
}

export default function MessageBubble({ message, isStreaming, onSend }: Props) {
  const isUser = message.role === "user";
  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);

  const handleOptionSelect = (optionId: string, optionTitle: string) => {
    setSelectedOptionId(optionId);
    onSend?.(`I'd like to go with: ${optionTitle}`);
  };

  const segments = isUser ? null : parseSegments(message.content);
  const hasTradeOffs = segments?.some((s) => s.kind === "trade_off") ?? false;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3 animate-fade-in`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center text-sm shrink-0 mt-0.5 mr-2">
          ✈️
        </div>
      )}
      <div className={`max-w-[85%] ${isUser ? "max-w-[70%]" : ""}`}>
        {isUser ? (
          <div className="rounded-2xl px-4 py-2.5 text-sm bg-primary-600 text-white rounded-br-sm">
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {segments?.map((seg, i) => {
              if (seg.kind === "trade_off") {
                return selectedOptionId ? (
                  <p key={i} className="text-xs text-slate-400 italic px-1">
                    Option selected ✓
                  </p>
                ) : (
                  <TradeOffOptions
                    key={i}
                    title={seg.title}
                    options={seg.options}
                    onSelect={(id) => {
                      const opt = seg.options.find((o) => o.id === id);
                      handleOptionSelect(id, opt?.title ?? id);
                    }}
                  />
                );
              }
              // Text segment — only wrap in bubble if there's actual content
              const trimmed = seg.content.trim();
              if (!trimmed) return null;
              return (
                <div
                  key={i}
                  className="rounded-2xl px-4 py-2.5 text-sm bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm"
                >
                  <div
                    className="prose-chat break-words"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(trimmed) }}
                  />
                  {isStreaming && i === segments.length - 1 && !message.content && (
                    <span className="inline-flex gap-0.5 py-1">
                      {[0, 1, 2].map((j) => (
                        <span
                          key={j}
                          className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-pulse-dot"
                          style={{ animationDelay: `${j * 0.16}s` }}
                        />
                      ))}
                    </span>
                  )}
                  {isStreaming && i === segments.length - 1 && message.content && (
                    <span className="typing-cursor" />
                  )}
                </div>
              );
            })}
            {/* Streaming placeholder when no content yet */}
            {isStreaming && !message.content && (
              <div className="rounded-2xl px-4 py-2.5 text-sm bg-white border border-slate-200 rounded-bl-sm shadow-sm">
                <span className="inline-flex gap-0.5 py-1">
                  {[0, 1, 2].map((j) => (
                    <span
                      key={j}
                      className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-pulse-dot"
                      style={{ animationDelay: `${j * 0.16}s` }}
                    />
                  ))}
                </span>
              </div>
            )}
          </div>
        )}
        {message.timestamp && (
          <p className={`text-xs text-slate-400 mt-1 ${isUser ? "text-right" : "text-left"}`}>
            {format(new Date(message.timestamp), "h:mm a")}
          </p>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-primary-600 flex items-center justify-center text-xs text-white font-bold shrink-0 mt-0.5 ml-2">
          U
        </div>
      )}
    </div>
  );
}
