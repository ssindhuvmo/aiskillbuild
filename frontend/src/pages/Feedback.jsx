import { useState } from "react";
import { sendFeedback } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import FilterChip from "../components/FilterChip.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";

// Mirrors core/schemas.py FeedbackArea and MAX_FEEDBACK.
const AREAS = [
  ["intake", "Intake"],
  ["skill_analysis", "Skill Analysis"],
  ["resources", "Resources"],
  ["roadmap", "Learning Roadmap"],
  ["report", "Transition Report"],
  ["dashboard", "Dashboard"],
  ["progress", "Progress Review"],
  ["job_match", "Job Match"],
  ["other", "Something else"],
];
const RATINGS = [
  [1, "Poor"],
  [2, "Fair"],
  [3, "Good"],
  [4, "Very good"],
  [5, "Excellent"],
];
const MAX_MESSAGE = 2000;

export default function Feedback() {
  const [rating, setRating] = useState(null);
  const [areas, setAreas] = useState([]); // none chosen = the whole platform
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    if (!message.trim()) return setError("Write a message before sending.");
    setSending(true);
    setError("");
    try {
      await sendFeedback({ rating, areas, message });
      setSent(true);
      setRating(null);
      setAreas([]);
      setMessage("");
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  // Keeps the chosen areas in the order of AREAS.
  const toggleArea = (value) =>
    setAreas((chosen) => AREAS.map(([v]) => v).filter((v) => (v === value ? !chosen.includes(v) : chosen.includes(v))));

  const header = <PageHeader title="Feedback" subtitle="Tell us what works, what doesn't and what you'd like to see." />;

  if (sent) {
    return (
      <>
        {header}
        <Notice>Thank you, your feedback was sent. We read every message.</Notice>
        <div className="row">
          <Button variant="secondary" onClick={() => setSent(false)}>Send more feedback</Button>
        </div>
      </>
    );
  }

  return (
    <>
      {header}
      <Card className="feedback-form">
        <form className="stack" onSubmit={submit} noValidate>
          <fieldset className="field-group">
            <legend>How is the platform so far? (optional)</legend>
            <div className="chips">
              {RATINGS.map(([value, label]) => (
                <FilterChip
                  key={value}
                  pressed={rating === value}
                  disabled={sending}
                  onClick={() => setRating(rating === value ? null : value)}
                >
                  <strong>{value}</strong>
                  <small>{label}</small>
                </FilterChip>
              ))}
            </div>
          </fieldset>

          <fieldset className="field-group">
            <legend>Which screens is it about? Choose any that apply (optional)</legend>
            <div className="chips">
              {AREAS.map(([value, label]) => (
                <FilterChip key={value} pressed={areas.includes(value)} disabled={sending} onClick={() => toggleArea(value)}>
                  {label}
                </FilterChip>
              ))}
            </div>
            <p className="muted" role="status">
              {areas.length ? `${areas.length} selected` : "None selected: your feedback is about the whole platform."}
            </p>
          </fieldset>

          <label className="field">
            Your feedback
            <textarea
              rows={6}
              required
              maxLength={MAX_MESSAGE}
              value={message}
              disabled={sending}
              aria-describedby="feedback-count"
              placeholder="What was useful, what was confusing, what went wrong, what's missing…"
              onChange={(e) => {
                setMessage(e.target.value);
                if (error) setError("");
              }}
            />
          </label>
          <p id="feedback-count" className="muted">{message.length} of {MAX_MESSAGE} characters</p>

          {error && <p className="error" role="alert">{error}</p>}

          <div className="row row-between">
            <p className="muted">
              Your feedback is saved with your account. If you use Start over, it is kept but no longer linked to you.
            </p>
            <Button type="submit" disabled={sending}>{sending ? "Sending…" : "Send feedback"}</Button>
          </div>
        </form>
      </Card>
    </>
  );
}
