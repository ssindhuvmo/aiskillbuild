import { useEffect, useId, useRef } from "react";
import Markdown from "react-markdown";
import Button from "./Button.jsx";

// A conversation: assistant and user bubbles, then the input. The parent owns the messages and
// the input text; `children` render under the last message (e.g. answer buttons).
export default function Chat({ messages, sending, waitingText = "…", value, onChange, onSend, disabled, label, placeholder, error, children }) {
  const bottom = useRef(null);
  const id = useId();

  useEffect(() => {
    // Scroll inside the log only, so the page doesn't jump; also after a reply finishes, so
    // the answer buttons come into view.
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, sending]);

  function submit(e) {
    e.preventDefault();
    if (value.trim() && !sending) onSend(value.trim());
  }

  return (
    <div className="chat">
      <div className="chat-log" tabIndex={0} aria-label="Conversation">
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            {m.role === "assistant" && m.content ? (
              // react-markdown escapes raw HTML by default (no rehype-raw), so this stays safe.
              <Markdown>{m.content}</Markdown>
            ) : (
              m.content || (sending ? waitingText : "")
            )}
          </div>
        ))}
        {children}
        <div ref={bottom} />
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <form className="chat-form" onSubmit={submit}>
        <label className="sr-only" htmlFor={id}>{label}</label>
        <input
          id={id}
          value={value}
          disabled={sending || disabled}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        <Button type="submit" disabled={sending || disabled || !value.trim()}>{sending ? "…" : "Send"}</Button>
      </form>
    </div>
  );
}
