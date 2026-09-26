import { useEffect, useRef, useState } from "react";
import { getIntake, streamChat } from "../api.js";
import ProfileSummary from "../components/ProfileSummary.jsx";

const GREETING =
  "Hi! I'll ask a few quick questions to build your profile: your current role, the AI role you're aiming for, what you already know about AI, the industry you work in, and how many hours a week you can study. Let's start — what's your current role?";

export default function Intake({ userId }) {
  const [messages, setMessages] = useState([]);
  const [profile, setProfile] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const bottom = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setProfile(null);
    setLoadError("");
    getIntake(userId)
      .then((s) => {
        if (cancelled) return;
        setMessages(s.messages);
        setProfile(s.profile);
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setError("");
    setSending(true);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    await streamChat(userId, text, {
      onToken: (t) =>
        setMessages((m) => {
          const copy = m.slice();
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + t };
          return copy;
        }),
      onState: setProfile,
      onError: setError,
    });
    setMessages((m) => (m.length && m[m.length - 1].content === "" ? m.slice(0, -1) : m));
    setSending(false);
  }

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!profile) return <main className="card"><p>Loading…</p></main>;

  const shown = messages.length === 0 ? [{ role: "assistant", content: GREETING }] : messages;

  return (
    <main className="intake">
      <section className="card chat">
        <div className="log">
          {shown.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>{m.content || (sending ? "…" : "")}</div>
          ))}
          <div ref={bottom} />
        </div>
        {error && <p className="error">{error}</p>}
        <form onSubmit={send}>
          <input
            value={input}
            disabled={sending}
            placeholder="Type your answer…"
            onChange={(e) => setInput(e.target.value)}
          />
          <button type="submit" disabled={sending || !input.trim()}>{sending ? "…" : "Send"}</button>
        </form>
      </section>
      <ProfileSummary userId={userId} profile={profile} onChange={setProfile} />
    </main>
  );
}
