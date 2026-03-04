"use client";

import { format } from "date-fns";
import type { ChatMessage } from "@/types";

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
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

export default function MessageBubble({ message, isStreaming }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3 animate-fade-in`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-primary-100 flex items-center justify-center text-sm shrink-0 mt-0.5 mr-2">
          ✈️
        </div>
      )}
      <div className={`max-w-[85%] ${isUser ? "max-w-[70%]" : ""}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm ${
            isUser
              ? "bg-primary-600 text-white rounded-br-sm"
              : "bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <div
              className="prose-chat break-words"
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(message.content),
              }}
            />
          )}
          {isStreaming && !message.content && (
            <span className="inline-flex gap-0.5 py-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-pulse-dot"
                  style={{ animationDelay: `${i * 0.16}s` }}
                />
              ))}
            </span>
          )}
          {isStreaming && message.content && (
            <span className="typing-cursor" />
          )}
        </div>
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
