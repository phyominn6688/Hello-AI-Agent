import { useEffect, useRef, useState } from "react";
import type { Alert, ItineraryDay, Message } from "../types";
import {
  getAlerts,
  getConversation,
  getItinerary,
  getTrip,
  markAlertRead,
  streamChat,
} from "../lib/api";
import MessageBubble from "../components/Message";
import TypingIndicator from "../components/TypingIndicator";
import ItinerarySheet from "../components/ItinerarySheet";
import AlertBanner from "../components/AlertBanner";

interface Props {
  tripId: number;
  onBack: () => void;
}

export default function Chat({ tripId, onBack }: Props) {
  const [tripTitle, setTripTitle] = useState("Trip");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [toolChip, setToolChip] = useState<string | null>(null);
  const [showSheet, setShowSheet] = useState(false);
  const [itinerary, setItinerary] = useState<ItineraryDay[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Current streaming assistant message buffer
  const streamingContent = useRef("");

  useEffect(() => {
    getTrip(tripId)
      .then((t) => setTripTitle(t.title))
      .catch(console.error);

    getConversation(tripId)
      .then((c) => setMessages(c.messages))
      .catch(console.error);

    getItinerary(tripId)
      .then(setItinerary)
      .catch(console.error);

    getAlerts(tripId)
      .then((a) => setAlerts(a.filter((x) => !x.read_at)))
      .catch(console.error);
  }, [tripId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const userMsg: Message = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);
    streamingContent.current = "";

    // Placeholder assistant message that we'll stream into
    const assistantPlaceholder: Message = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, assistantPlaceholder]);

    try {
      for await (const event of streamChat(tripId, text)) {
        if (event.type === "text") {
          streamingContent.current += event.content;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: streamingContent.current,
            };
            return updated;
          });
        } else if (event.type === "tool_use") {
          setToolChip(formatToolName(event.tool));
        } else if (event.type === "tool_result") {
          // Fade chip out after result arrives
          setTimeout(() => setToolChip(null), 1500);
        } else if (event.type === "done") {
          // Refresh itinerary after agent response
          getItinerary(tripId).then(setItinerary).catch(console.error);
        } else if (event.type === "error") {
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: "assistant",
              content: "Sorry, something went wrong. Please try again.",
            };
            return updated;
          });
        }
      }
    } catch (err) {
      console.error("Stream error:", err);
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "Connection error. Please check your network and try again.",
        };
        return updated;
      });
    } finally {
      setStreaming(false);
      setToolChip(null);
    }
  };

  const dismissAlert = async (alertId: number) => {
    setAlerts((prev) => prev.filter((a) => a.id !== alertId));
    try {
      await markAlertRead(tripId, alertId);
    } catch {
      // ignore
    }
  };

  const isLastMessageEmpty =
    messages.length > 0 &&
    messages[messages.length - 1].role === "assistant" &&
    messages[messages.length - 1].content === "" &&
    streaming;

  return (
    <div className="chat-screen">
      <div className="chat-header">
        <button className="btn-icon" onClick={onBack}>‹</button>
        <span className="chat-header-title">{tripTitle}</span>
        <button
          className="btn-icon"
          onClick={() => setShowSheet(true)}
          title="Itinerary"
        >
          📋
        </button>
      </div>

      {alerts.map((alert) => (
        <AlertBanner
          key={alert.id}
          alert={alert}
          onDismiss={() => dismissAlert(alert.id)}
        />
      ))}

      <div className="messages-list">
        {messages.map((msg, i) => {
          const isStreaming =
            i === messages.length - 1 && streaming && msg.role === "assistant";
          if (isLastMessageEmpty && i === messages.length - 1) return null;
          return (
            <MessageBubble
              key={i}
              message={msg}
              isStreaming={isStreaming}
            />
          );
        })}

        {toolChip && (
          <div className="tool-chip">
            <span>🔍</span>
            <span>{toolChip}</span>
          </div>
        )}

        {isLastMessageEmpty && <TypingIndicator />}

        <div ref={bottomRef} className="messages-bottom" />
      </div>

      <div className="chat-input-bar">
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          placeholder="Ask anything about your trip…"
          rows={1}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            autoResize();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          }}
          disabled={streaming}
        />
        <button
          className="btn-send"
          onClick={sendMessage}
          disabled={!input.trim() || streaming}
        >
          ▶
        </button>
      </div>

      {showSheet && (
        <ItinerarySheet
          itinerary={itinerary}
          onClose={() => setShowSheet(false)}
        />
      )}
    </div>
  );
}

function formatToolName(tool: string): string {
  return tool
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
