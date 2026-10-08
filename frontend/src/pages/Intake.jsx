import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { AI_EXPERIENCE } from "../aiExperience.js";
import { getIntake, streamChat } from "../api.js";
import ProfileSummary from "../components/ProfileSummary.jsx";

const GREETING =
  "Hi! I'll ask a few quick questions to build your profile: your current role, the AI role you're aiming for, your experience with AI, the industry you work in, and how many hours a week you can study. Let's start — what's your current role?";

export default function Intake() {
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
    getIntake()
      .then((s) => {
        if (cancelled) return;
        setMessages(s.messages);
        setProfile(s.profile);
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]); // also after a reply finishes, so the answer buttons scroll into view

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    await sendText(text);
  }

  async function sendText(text) {
    if (sending) return;
    setError("");
    setSending(true);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    await streamChat("/api/intake/chat", text, {
      onToken: (t) =>
        setMessages((m) => {
          const copy = m.slice();
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + t };
          return copy;
        }),
      onState: (evt) => setProfile(evt.profile),
      onError: setError,
    });
    setMessages((m) => (m.length && m[m.length - 1].content === "" ? m.slice(0, -1) : m));
    setSending(false);
  }

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!profile) return <main className="card"><p>Loading…</p></main>;

  const shown = messages.length === 0 ? [{ role: "assistant", content: GREETING }] : messages;
  // The agent asks fields in order, so AI experience being the first missing field means
  // the latest question is about it. Typing an answer instead still works.
  const showExperience =
    !sending && profile.missing[0] === "ai_experience" && shown[shown.length - 1].role === "assistant";

  return (
    <main className="intake">
      <section className="card chat">
        <div className="log">
          {shown.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.role === "assistant" && m.content ? (
                // react-markdown escapes raw HTML by default (no rehype-raw), so this stays safe.
                <Markdown>{m.content}</Markdown>
              ) : (
                m.content || (sending ? "…" : "")
              )}
            </div>
          ))}
          {showExperience && (
            <div className="choices">
              {AI_EXPERIENCE.map((o) => (
                <button key={o.value} type="button" className="choice" onClick={() => sendText(o.value)}>
                  <strong>{o.value}</strong>
                  <span>{o.hint}</span>
                </button>
              ))}
            </div>
          )}
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
      <ProfileSummary profile={profile} onChange={setProfile} />
    </main>
  );
}
