import { type ReactNode } from "react";
import { format } from "date-fns";
import type { Message } from "../types";

interface Props {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`message-row ${message.role}`}>
      <div className={`message-bubble ${message.role}`}>
        {isUser ? (
          <span>{message.content}</span>
        ) : (
          <MarkdownText text={message.content} />
        )}
        {isStreaming && <span className="cursor-blink">▌</span>}
      </div>
      {message.timestamp && (
        <div className="message-time">
          {format(new Date(message.timestamp), "h:mm a")}
        </div>
      )}
    </div>
  );
}

/**
 * Minimal markdown renderer — handles bold, italic, inline code,
 * unordered lists, ordered lists, and paragraphs.
 * No dependencies — pure string parsing.
 */
function MarkdownText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);

  return (
    <>
      {blocks.map((block, bi) => {
        // Unordered list
        if (/^[-*+] /m.test(block)) {
          const items = block.split("\n").filter((l) => /^[-*+] /.test(l));
          return (
            <ul key={bi}>
              {items.map((item, ii) => (
                <li key={ii}>
                  <InlineMarkdown text={item.replace(/^[-*+] /, "")} />
                </li>
              ))}
            </ul>
          );
        }

        // Ordered list
        if (/^\d+\. /m.test(block)) {
          const items = block.split("\n").filter((l) => /^\d+\. /.test(l));
          return (
            <ol key={bi}>
              {items.map((item, ii) => (
                <li key={ii}>
                  <InlineMarkdown text={item.replace(/^\d+\. /, "")} />
                </li>
              ))}
            </ol>
          );
        }

        return (
          <p key={bi}>
            <InlineMarkdown text={block} />
          </p>
        );
      })}
    </>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  // Parse inline: **bold**, *italic*, `code`
  const parts: (string | ReactNode)[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const raw = match[0];
    if (raw.startsWith("**")) {
      parts.push(<strong key={match.index}>{raw.slice(2, -2)}</strong>);
    } else if (raw.startsWith("`")) {
      parts.push(<code key={match.index}>{raw.slice(1, -1)}</code>);
    } else if (raw.startsWith("*")) {
      parts.push(<em key={match.index}>{raw.slice(1, -1)}</em>);
    }
    lastIndex = match.index + raw.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <>{parts}</>;
}
