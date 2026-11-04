import { useContext, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CAPABILITY_AREAS, describeConstraints, describePreferences, ratedCount } from "../capabilities.js";
import { confirmProfile, getDomains, updateProfile } from "../api.js";
import { ProfileContext } from "../profileContext.js";
import Button from "./Button.jsx";
import Card from "./Card.jsx";
import { CapabilityRatings, cleanConstraints, ConstraintsInput, PreferenceChips } from "./ProfileInputs.jsx";
import { resumeCounts } from "./ResumeUpload.jsx";

const AREAS = Object.keys(CAPABILITY_AREAS);

// What the card shows for each field; `empty` is the text while it has no value.
const ROWS = [
  { key: "target_role", label: "Target role" },
  { key: "current_role", label: "Current role" },
  { key: "years_experience", label: "Experience", show: (v) => `${v} year${v === 1 ? "" : "s"}` },
  { key: "domain", label: "Industry domain" },
  { key: "hours_per_week", label: "Hours per week" },
  { key: "capabilities", label: "Capability assessment" },
  { key: "learning_preferences", label: "Learning preferences", show: describePreferences, empty: "Not asked yet" },
  { key: "constraints", label: "Budget and constraints", show: describeConstraints, empty: "Optional" },
  { key: "additional_context", label: "Additional context", show: (v) => v || "Nothing added", empty: "Optional" },
];

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

function Capabilities({ value }) {
  const rated = ratedCount(value);
  if (rated === 0) return <dd className="empty">Not rated yet</dd>;
  return (
    <dd>
      <div className={rated < AREAS.length ? "muted" : ""}>{rated} of {AREAS.length} rated</div>
      <ul className="plain-list">
        {AREAS.filter((a) => value[a]).map((a) => <li key={a}>{CAPABILITY_AREAS[a]}: {value[a]}</li>)}
      </ul>
    </dd>
  );
}

function Resume({ resume, profile, onReview }) {
  if (resume.status === "none") return <dd className="empty">{profile.resume_skipped ? "Skipped" : "Not uploaded"}</dd>;
  return (
    <dd>
      <div className="file-name">{resume.filename}</div>
      <div className="muted">
        {resume.status === "review" ? "Waiting for your review" : `Read: ${resumeCounts(resume.data)}`}
      </div>
      {onReview && resume.status === "reviewed" && <Button variant="text" className="inline-btn" onClick={onReview}>Review again</Button>}
    </dd>
  );
}

// The Career Profile card: what the intake has collected so far, with Edit and Confirm. Editable
// at any time; an edit un-confirms the profile and marks later steps out of date.
export default function ProfileSummary({ profile, resume, onChange, onReviewResume }) {
  const { user } = useContext(ProfileContext);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({});
  const [domains, setDomains] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getDomains().then((d) => setDomains(d.domains)).catch(() => {});
  }, []);

  const reviewPending = profile.resume_status === "review";
  const complete = profile.missing.length === 0 && !reviewPending;

  function startEdit() {
    setForm({
      ...profile,
      capabilities: { ...profile.capabilities },
      learning_preferences: profile.learning_preferences ?? [],
      constraints: { ...(profile.constraints ?? {}) },
      additional_context: profile.additional_context ?? "",
    });
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
    for (const k of ["current_role", "target_role", "years_experience", "domain", "hours_per_week"]) {
      if (form[k] !== profile[k] && form[k] !== "" && form[k] != null) fields[k] = form[k];
    }
    const caps = Object.fromEntries(AREAS.filter((a) => form.capabilities[a] !== profile.capabilities[a]).map((a) => [a, form.capabilities[a]]));
    if (Object.keys(caps).length) fields.capabilities = caps;
    // An optional answer left empty stays "not asked yet" rather than being saved as none.
    if (!same(form.learning_preferences, profile.learning_preferences ?? [])) fields.learning_preferences = form.learning_preferences;
    const constraints = cleanConstraints(form.constraints);
    if (!same(constraints, profile.constraints ?? {})) fields.constraints = constraints;
    const context = form.additional_context.trim();
    if (context !== (profile.additional_context ?? "")) fields.additional_context = context;
    if (Object.keys(fields).length === 0 || (await run(() => updateProfile(fields)))) setEditing(false);
  }

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const fromResume = (k) => profile.field_sources[k] === "resume" && <span className="source"> · from resume</span>;

  return (
    <Card as="aside" title="Career Profile" aria-label="Career Profile" className="split-side">
      {editing ? (
        <>
          <label className="field">Target role<input value={form.target_role ?? ""} onChange={set("target_role")} /></label>
          <label className="field">Current role<input value={form.current_role ?? ""} onChange={set("current_role")} /></label>
          <label className="field">Years of experience<input type="number" min="0" max="50" value={form.years_experience ?? ""} onChange={set("years_experience")} /></label>
          <label className="field">Industry domain
            <input list="domains" value={form.domain ?? ""} onChange={set("domain")} />
            <datalist id="domains">{domains.filter((d) => d !== "Other").map((d) => <option key={d} value={d} />)}</datalist>
          </label>
          <label className="field">Hours per week<input type="number" min="1" max="40" value={form.hours_per_week ?? ""} onChange={set("hours_per_week")} /></label>
          <fieldset className="field-group">
            <legend>Capability assessment</legend>
            <CapabilityRatings value={form.capabilities} onRate={(a, l) => setForm({ ...form, capabilities: { ...form.capabilities, [a]: l } })} />
          </fieldset>
          <fieldset className="field-group">
            <legend>Learning preferences</legend>
            <PreferenceChips value={form.learning_preferences} onChange={(v) => setForm({ ...form, learning_preferences: v })} />
          </fieldset>
          <fieldset className="field-group">
            <legend>Budget and constraints</legend>
            <ConstraintsInput value={form.constraints} onChange={(v) => setForm({ ...form, constraints: v })} />
          </fieldset>
          <label className="field">Additional context
            <textarea rows={4} maxLength={2000} value={form.additional_context} onChange={set("additional_context")} />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="row">
            <Button onClick={save} disabled={busy}>Save</Button>
            <Button variant="secondary" onClick={() => setEditing(false)} disabled={busy}>Cancel</Button>
          </div>
        </>
      ) : (
        <>
          <dl className="fields">
            {user?.name && (
              <div>
                <dt>Name</dt>
                <dd>{user.name}</dd>
              </div>
            )}
            {ROWS.map(({ key, label, show = (v) => v, empty = "Not collected yet" }) => (
              <div key={key}>
                <dt>{label}{fromResume(key)}</dt>
                {key === "capabilities" ? (
                  <Capabilities value={profile.capabilities} />
                ) : (
                  <dd className={profile[key] == null ? "empty" : ""}>{profile[key] == null ? empty : show(profile[key])}</dd>
                )}
              </div>
            ))}
            <div>
              <dt>Resume</dt>
              <Resume resume={resume} profile={profile} onReview={onReviewResume} />
            </div>
          </dl>
          {error && <p className="error" role="alert">{error}</p>}
          {reviewPending && <p className="muted">Finish reviewing your resume before confirming.</p>}
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
