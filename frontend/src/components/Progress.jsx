import { useEffect, useState } from "react";

// Rotates friendly status lines while a long AI request runs.
export default function Progress({ messages, note, interval = 6000 }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => Math.min(n + 1, messages.length - 1)), interval);
    return () => clearInterval(t);
  }, [messages.length, interval]);
  return (
    <div className="card progress" aria-live="polite">
      <div className="bar"><span /></div>
      <p className="progress-msg">{messages[i]}</p>
      <p className="muted">{note}</p>
    </div>
  );
}
