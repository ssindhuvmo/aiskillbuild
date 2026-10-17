import { useContext, useEffect, useState } from "react";
import { AI_EXPERIENCE } from "../aiExperience.js";
import { getIntake, streamChat } from "../api.js";
import Card from "../components/Card.jsx";
import Chat from "../components/Chat.jsx";
import FilterChip from "../components/FilterChip.jsx";
import PageHeader from "../components/PageHeader.jsx";
import ProfileSummary, { LABELS } from "../components/ProfileSummary.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import { ProfileContext } from "../profileContext.js";

const GREETING =
  "Hi! I'll ask a few quick questions to build your profile: your current role, the AI role you're aiming for, your experience with AI, the industry you work in, and how many hours a week you can study. Let's start — what's your current role?";

const QUESTIONS = Object.keys(LABELS).length;

export default function Intake() {
  const [messages, setMessages] = useState([]);
  const [profile, setProfile] = useState(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const { setProfile: shareProfile } = useContext(ProfileContext);

  // Every profile change also updates the sidebar's profile card.
  function applyProfile(p) {
    setProfile(p);
    shareProfile(p);
  }

  useEffect(() => {
    let cancelled = false;
    setProfile(null);
    setLoadError("");
    getIntake()
      .then((s) => {
        if (cancelled) return;
        setMessages(s.messages);
        applyProfile(s.profile);
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  async function sendText(text) {
    if (sending) return;
    setInput("");
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
      onState: (evt) => applyProfile(evt.profile),
      onError: setError,
    });
    setMessages((m) => (m.length && m[m.length - 1].content === "" ? m.slice(0, -1) : m));
    setSending(false);
  }

  const header = (children) => (
    <PageHeader title="Intake" subtitle="Tell us where you are and where you want to go.">{children}</PageHeader>
  );

  if (loadError) return <>{header()}<Card><p className="error" role="alert">{loadError}</p></Card></>;
  if (!profile) return <>{header()}<Card><p>Loading…</p></Card></>;

  const shown = messages.length === 0 ? [{ role: "assistant", content: GREETING }] : messages;
  // The agent asks fields in order, so AI experience being the first missing field means
  // the latest question is about it. Typing an answer instead still works.
  const showExperience =
    !sending && profile.missing[0] === "ai_experience" && shown[shown.length - 1].role === "assistant";
  const answered = QUESTIONS - profile.missing.length;
  const next = profile.missing.length ? `Next: ${LABELS[profile.missing[0]]}` : profile.confirmed ? "Profile confirmed" : "Ready to confirm";

  return (
    <>
      {header(
        <div className="header-progress">
          <div className="header-progress-text">
            <span>{answered} of {QUESTIONS} answered</span>
            <span>{next}</span>
          </div>
          <ProgressBar value={answered} max={QUESTIONS} label="Question progress" />
        </div>
      )}
      <div className="split">
        <Card aria-label="Conversation" className="split-main">
          <Chat
            messages={shown}
            sending={sending}
            value={input}
            onChange={setInput}
            onSend={sendText}
            label="Your answer"
            placeholder="Type your answer…"
            error={error}
          >
            {showExperience && (
              <div className="chips" role="group" aria-label="AI experience">
                {AI_EXPERIENCE.map((o) => (
                  <FilterChip key={o.value} pressed={profile.ai_experience === o.value} onClick={() => sendText(o.value)}>
                    <strong>{o.value}</strong>
                    <small>{o.hint}</small>
                  </FilterChip>
                ))}
              </div>
            )}
          </Chat>
        </Card>
        <ProfileSummary profile={profile} onChange={applyProfile} />
      </div>
    </>
  );
}
