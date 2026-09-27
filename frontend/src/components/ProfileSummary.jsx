import { useEffect, useState } from "react";
import { AI_EXPERIENCE } from "../aiExperience.js";
import { confirmProfile, getDomains, updateProfile } from "../api.js";

const LABELS = {
  current_role: "Current role",
  target_role: "Target role",
  ai_experience: "AI experience",
  domain: "Domain",
  hours_per_week: "Hours / week",
};

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
    <aside className="card summary">
      <h2>Your profile</h2>
      {editing ? (
        <div className="edit">
          <label>Current role<input value={form.current_role ?? ""} onChange={set("current_role")} /></label>
          <label>Target role<input value={form.target_role ?? ""} onChange={set("target_role")} /></label>
          <label>AI experience
            <select value={form.ai_experience ?? ""} onChange={set("ai_experience")}>
              <option value="">—</option>
              {AI_EXPERIENCE.map((o) => <option key={o.value} value={o.value}>{o.value} — {o.hint}</option>)}
            </select>
          </label>
          <label>Domain
            <input list="domains" value={form.domain ?? ""} onChange={set("domain")} />
            <datalist id="domains">{domains.filter((d) => d !== "Other").map((d) => <option key={d} value={d} />)}</datalist>
          </label>
          <label>Hours / week<input type="number" min="1" max="40" value={form.hours_per_week ?? ""} onChange={set("hours_per_week")} /></label>
          {error && <p className="error">{error}</p>}
          <div className="row">
            <button onClick={save} disabled={busy}>Save</button>
            <button className="secondary" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          <dl>
            {Object.entries(LABELS).map(([k, label]) => (
              <div key={k}>
                <dt>{label}</dt>
                <dd className={profile[k] == null ? "empty" : ""}>{profile[k] ?? "not collected yet"}</dd>
              </div>
            ))}
          </dl>
          {error && <p className="error">{error}</p>}
          <div className="row">
            <button className="secondary" onClick={startEdit}>Edit</button>
            <button onClick={() => run(() => confirmProfile())} disabled={!complete || profile.confirmed || busy}>
              {profile.confirmed ? "Confirmed ✓" : "Confirm"}
            </button>
          </div>
          {profile.confirmed && <p className="ok">Profile saved. Skill-gap analysis arrives in the next milestone.</p>}
        </>
      )}
    </aside>
  );
}
