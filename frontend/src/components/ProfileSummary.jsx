import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AI_EXPERIENCE } from "../aiExperience.js";
import { confirmProfile, getDomains, updateProfile } from "../api.js";
import Button from "./Button.jsx";
import Card from "./Card.jsx";

// The profile fields in the order the intake chat asks for them.
export const LABELS = {
  current_role: "Current role",
  target_role: "Target role",
  ai_experience: "AI experience",
  domain: "Industry domain",
  hours_per_week: "Hours per week",
};

// The Profile Card: what the intake has collected so far, with Edit and Confirm.
export default function ProfileSummary({ profile, onChange }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [domains, setDomains] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getDomains().then((d) => setDomains(d.domains)).catch(() => {});
  }, []);

  const complete = profile.missing.length === 0;

  function startEdit() {
    setForm({ ...profile });
    setError("");
    setEditing(true);
  }

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      onChange(await fn());
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const fields = {};
    for (const k of Object.keys(LABELS)) {
      if (form[k] !== profile[k] && form[k] !== "" && form[k] != null) fields[k] = form[k];
    }
    if (Object.keys(fields).length === 0 || (await run(() => updateProfile(fields)))) setEditing(false);
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  return (
    <Card as="aside" title="Profile summary" aria-label="Profile summary" className="split-side">
      {editing ? (
        <>
          <label className="field">{LABELS.current_role}<input value={form.current_role ?? ""} onChange={set("current_role")} /></label>
          <label className="field">{LABELS.target_role}<input value={form.target_role ?? ""} onChange={set("target_role")} /></label>
          <label className="field">{LABELS.ai_experience}
            <select value={form.ai_experience ?? ""} onChange={set("ai_experience")}>
              <option value="">—</option>
              {AI_EXPERIENCE.map((o) => <option key={o.value} value={o.value}>{o.value} — {o.hint}</option>)}
            </select>
          </label>
          <label className="field">{LABELS.domain}
            <input list="domains" value={form.domain ?? ""} onChange={set("domain")} />
            <datalist id="domains">{domains.filter((d) => d !== "Other").map((d) => <option key={d} value={d} />)}</datalist>
          </label>
          <label className="field">{LABELS.hours_per_week}<input type="number" min="1" max="40" value={form.hours_per_week ?? ""} onChange={set("hours_per_week")} /></label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="row">
            <Button onClick={save} disabled={busy}>Save</Button>
            <Button variant="secondary" onClick={() => setEditing(false)} disabled={busy}>Cancel</Button>
          </div>
        </>
      ) : (
        <>
          <dl className="fields">
            {Object.entries(LABELS).map(([k, label]) => (
              <div key={k}>
                <dt>{label}</dt>
                <dd className={profile[k] == null ? "empty" : ""}>{profile[k] ?? "Not collected yet"}</dd>
              </div>
            ))}
          </dl>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="row">
            <Button variant="secondary" onClick={startEdit}>Edit</Button>
            <Button onClick={() => run(() => confirmProfile())} disabled={!complete || profile.confirmed || busy}>
              {profile.confirmed ? "Confirmed ✓" : "Confirm"}
            </Button>
          </div>
          {profile.confirmed && (
            <p className="ok">
              Profile saved. <Link to="/gaps">Continue to Skill Analysis →</Link>
            </p>
          )}
        </>
      )}
    </Card>
  );
}
