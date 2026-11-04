import { useContext, useEffect, useState } from "react";
import { deleteResume, getIntake, getResume, streamChat } from "../api.js";
import Card from "../components/Card.jsx";
import Chat from "../components/Chat.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import IntakeStep from "../components/IntakeStep.jsx";
import PageHeader from "../components/PageHeader.jsx";
import ProfileSummary from "../components/ProfileSummary.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import ResumeReview from "../components/ResumeReview.jsx";
import { ProfileContext } from "../profileContext.js";

const GREETING =
  "Hi! I'll build your Career Profile in a few short steps: your goal, your resume, your background, the hours you can study, how you rate your skills today, how you like to learn, and any constraints. Let's start: which AI role are you aiming for? If you're not sure, say so and I'll suggest a few that fit you.";

export default function Intake() {
  const [messages, setMessages] = useState([]);
  const [profile, setProfile] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [resume, setResume] = useState(null); // ResumeState
  const [reviewAgain, setReviewAgain] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [discardError, setDiscardError] = useState("");
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
    Promise.all([getIntake(), getResume()])
      .then(([s, r]) => {
        if (cancelled) return;
        setMessages(s.messages);
        setSuggestions(s.suggestions);
        setResume(r);
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
      onState: (evt) => {
        applyProfile(evt.profile);
        setSuggestions(evt.suggestions ?? []);
      },
      onError: setError,
    });
    setMessages((m) => (m.length && m[m.length - 1].content === "" ? m.slice(0, -1) : m));
    setSending(false);
  }

  // Every resume change (upload, save, discard) returns the updated profile too.
  function applyResume(r) {
    setResume(r);
    applyProfile(r.profile);
  }

  function savedResume(r) {
    const firstReview = resume.status === "review";
    applyResume(r);
    setReviewAgain(false);
    // The chat moves on to confirming what the resume filled in.
    if (firstReview) sendText("I've reviewed my resume.");
  }

  async function discardResume() {
    setDiscarding(true);
    setDiscardError("");
    try {
      applyResume(await deleteResume());
      setReviewAgain(false);
      setConfirmDiscard(false);
    } catch (e) {
      setDiscardError(e.message);
    } finally {
      setDiscarding(false);
    }
  }

  const header = (children) => (
    <PageHeader title="Intake" subtitle="Tell us where you are and where you want to go.">{children}</PageHeader>
  );

  if (loadError) return <>{header()}<Card><p className="error" role="alert">{loadError}</p></Card></>;
  if (!profile || !resume) return <>{header()}<Card><p>Loading…</p></Card></>;

  const shown = messages.length === 0 ? [{ role: "assistant", content: GREETING }] : messages;
  // The agent follows next_step, so the widget for that step answers the latest question.
  // Typing an answer instead still works.
  const showStep = !sending && profile.next_step && shown[shown.length - 1].role === "assistant";
  const total = profile.steps.length;
  const answered = profile.steps.filter((st) => st.done).length;
  const current = profile.steps.find((st) => st.id === profile.next_step);
  const next = current ? current.label : profile.confirmed ? "Profile confirmed" : "Ready to confirm";
  const position = current ? `Question ${answered + 1} of ${total}` : `${answered} of ${total} done`;
  const reviewing = resume.status === "review" || (reviewAgain && resume.status === "reviewed");

  return (
    <>
      {header(
        <div className="header-progress">
          <div className="header-progress-text">
            <span>{position}</span>
            <span>{next}</span>
          </div>
          <ProgressBar value={answered} max={total} label="Question progress" />
        </div>
      )}
      {confirmDiscard && (
        <ConfirmDialog
          title="Discard your resume?"
          confirmLabel="Discard"
          busyLabel="Discarding…"
          busy={discarding}
          error={discardError}
          onCancel={() => setConfirmDiscard(false)}
          onConfirm={discardResume}
        >
          <p>The file and everything read from it are deleted. Values already in your profile stay; you can edit them.</p>
        </ConfirmDialog>
      )}
      <div className="split">
        {reviewing ? (
          <ResumeReview
            key={`${resume.uploaded_at}-${resume.status}`}
            resume={resume}
            onSaved={savedResume}
            onDiscard={() => { setDiscardError(""); setConfirmDiscard(true); }}
            onCancel={resume.status === "reviewed" ? () => setReviewAgain(false) : null}
          />
        ) : (
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
              {showStep && (
                <IntakeStep
                  key={profile.next_step}
                  step={profile.next_step}
                  profile={profile}
                  resume={resume}
                  suggestions={suggestions}
                  onProfile={applyProfile}
                  onResume={applyResume}
                  onSend={sendText}
                />
              )}
            </Chat>
          </Card>
        )}
        <ProfileSummary
          profile={profile}
          resume={resume}
          onChange={applyProfile}
          onReviewResume={reviewing ? null : () => setReviewAgain(true)}
        />
      </div>
    </>
  );
}
