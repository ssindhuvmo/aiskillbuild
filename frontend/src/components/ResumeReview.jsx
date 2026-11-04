import { useId, useState } from "react";
import { saveResume } from "../api.js";
import Button from "./Button.jsx";
import Card from "./Card.jsx";
import Notice from "./Notice.jsx";
import SkillBadge from "./SkillBadge.jsx";

const DATE = /^\d{4}(-(0[1-9]|1[0-2]))?$/; // must match resume_parser/schemas.py
const EMPTY = {
  roles: { title: "", employer: "", start: "", end: "", highlights: [] },
  education: { qualification: "", institution: "", year: "" },
  certifications: { name: "", issuer: "", year: "" },
};

// Form values are strings; the API takes nulls and numbers.
function toForm(data) {
  const str = (v) => (v == null ? "" : String(v));
  return {
    ...data,
    industry: str(data.industry),
    roles: data.roles.map((r) => ({ ...r, end: str(r.end) })),
    education: data.education.map((e) => ({ ...e, year: str(e.year) })),
    certifications: data.certifications.map((c) => ({ ...c, issuer: str(c.issuer), year: str(c.year) })),
  };
}

// Trimmed, without empty rows; returns [data, problem].
function fromForm(form) {
  const t = (v) => v.trim();
  const year = (v) => (t(v) ? Number(t(v)) : null);
  const roles = form.roles
    .map((r) => ({ ...r, title: t(r.title), employer: t(r.employer), start: t(r.start), end: t(r.end) || null }))
    .filter((r) => r.title || r.employer || r.start);
  for (const r of roles) {
    if (!r.title || !r.employer || !r.start) return [null, "Each role needs a title, an employer and a start date."];
    if (!DATE.test(r.start) || (r.end && !DATE.test(r.end))) return [null, `Write the dates of "${r.title}" as YYYY-MM or YYYY.`];
  }
  const education = form.education
    .map((e) => ({ qualification: t(e.qualification), institution: t(e.institution), year: year(e.year) }))
    .filter((e) => e.qualification || e.institution);
  if (education.some((e) => !e.qualification || !e.institution)) return [null, "Each education entry needs a qualification and an institution."];
  const certifications = form.certifications
    .map((c) => ({ name: t(c.name), issuer: t(c.issuer) || null, year: year(c.year) }))
    .filter((c) => c.name);
  if ([...education, ...certifications].some((x) => x.year !== null && !Number.isInteger(x.year))) return [null, "Years must be whole numbers, e.g. 2019."];
  const data = {
    skills: form.skills,
    roles,
    education,
    certifications,
    achievements: form.achievements.map(t).filter(Boolean),
    industry: t(form.industry) || null,
  };
  return [data, null];
}

// One editable list section: rows of inputs with Remove, and an Add button.
function Rows({ title, items, fields, blank, onChange, addLabel, empty }) {
  const id = useId();
  const set = (i, key, value) => onChange(items.map((item, j) => (j === i ? { ...item, [key]: value } : item)));
  return (
    <fieldset className="field-group review-section">
      <legend>{title}</legend>
      {items.length === 0 && <p className="muted">{empty}</p>}
      {items.map((item, i) => (
        <div key={i} className="edit-row">
          {fields.map(([key, label, placeholder]) => (
            <label key={key} className="field" htmlFor={`${id}-${i}-${key}`}>
              {label}
              <input id={`${id}-${i}-${key}`} value={item[key]} placeholder={placeholder} onChange={(e) => set(i, key, e.target.value)} />
            </label>
          ))}
          <Button variant="quiet" aria-label={`Remove ${title.toLowerCase()} ${i + 1}`} onClick={() => onChange(items.filter((_, j) => j !== i))}>
            Remove
          </Button>
        </div>
      ))}
      <div><Button variant="text" onClick={() => onChange([...items, { ...blank }])}>{addLabel}</Button></div>
    </fieldset>
  );
}

// [key, label, placeholder] per input.
const FIELDS = {
  roles: [["title", "Job title"], ["employer", "Employer"], ["start", "Start", "YYYY-MM"], ["end", "End", "Present"]],
  education: [["qualification", "Qualification"], ["institution", "Institution"], ["year", "Year"]],
  certifications: [["name", "Certification"], ["issuer", "Issuer"], ["year", "Year"]],
};

// The review screen after an upload: everything the parser read, editable, then Save or Discard.
// Only what the user saves here is used by the rest of the app.
export default function ResumeReview({ resume, onSaved, onDiscard, onCancel }) {
  const [form, setForm] = useState(() => toForm(resume.data));
  const [skill, setSkill] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const id = useId();
  const set = (key) => (value) => setForm({ ...form, [key]: value });

  function addSkill(e) {
    e.preventDefault();
    const s = skill.trim();
    if (s && !form.skills.some((x) => x.toLowerCase() === s.toLowerCase())) set("skills")([...form.skills, s]);
    setSkill("");
  }

  async function save() {
    const [data, problem] = fromForm(form);
    if (problem) return setError(problem);
    setBusy(true);
    setError("");
    try {
      onSaved(await saveResume(data));
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <Card className="split-main" aria-labelledby={`${id}-title`}>
      <div className="stack-tight">
        <h2 id={`${id}-title`}>Check what we read from your resume</h2>
        <p className="muted">
          {resume.filename}. Fix anything that's wrong, remove what doesn't belong and add what's missing. Only what you save
          here is used for your plan.
        </p>
      </div>
      {resume.dropped.length > 0 && (
        <Notice>
          We couldn't find these in your resume text, so we left them out. Add anything that's missing below.
          <ul className="plain-list">{resume.dropped.map((d) => <li key={d}>{d}</li>)}</ul>
        </Notice>
      )}

      <fieldset className="field-group review-section">
        <legend>Skills</legend>
        <div className="badges">
          {form.skills.map((s) => (
            <SkillBadge key={s} onRemove={() => set("skills")(form.skills.filter((x) => x !== s))} removeLabel={`Remove ${s}`}>{s}</SkillBadge>
          ))}
          {form.skills.length === 0 && <p className="muted">No skills yet.</p>}
        </div>
        <form className="chat-form" onSubmit={addSkill}>
          <label className="sr-only" htmlFor={`${id}-skill`}>Add a skill</label>
          <input id={`${id}-skill`} value={skill} maxLength={80} placeholder="Add a skill" onChange={(e) => setSkill(e.target.value)} />
          <Button type="submit" variant="secondary" disabled={!skill.trim() || form.skills.length >= 60}>Add</Button>
        </form>
      </fieldset>

      <Rows title="Roles" items={form.roles} fields={FIELDS.roles} blank={EMPTY.roles} onChange={set("roles")} addLabel="Add a role"
        empty="No roles yet. Leave End empty for your current role." />
      {resume.years_experience != null && (
        <p className="muted">Experience calculated from your roles: {resume.years_experience} years (overlapping roles count once).</p>
      )}
      <Rows title="Education" items={form.education} fields={FIELDS.education} blank={EMPTY.education} onChange={set("education")} addLabel="Add education"
        empty="No education yet." />
      <Rows title="Certifications" items={form.certifications} fields={FIELDS.certifications} blank={EMPTY.certifications} onChange={set("certifications")}
        addLabel="Add a certification" empty="No certifications yet." />

      <fieldset className="field-group review-section">
        <legend>Achievements</legend>
        {form.achievements.length === 0 && <p className="muted">No achievements yet.</p>}
        {form.achievements.map((a, i) => (
          <div key={i} className="edit-row">
            <label className="field" htmlFor={`${id}-ach-${i}`}>
              <span className="sr-only">Achievement {i + 1}</span>
              <input id={`${id}-ach-${i}`} value={a} maxLength={300}
                onChange={(e) => set("achievements")(form.achievements.map((x, j) => (j === i ? e.target.value : x)))} />
            </label>
            <Button variant="quiet" aria-label={`Remove achievement ${i + 1}`}
              onClick={() => set("achievements")(form.achievements.filter((_, j) => j !== i))}>Remove</Button>
          </div>
        ))}
        <div><Button variant="text" onClick={() => set("achievements")([...form.achievements, ""])}>Add an achievement</Button></div>
      </fieldset>

      <label className="field review-section" htmlFor={`${id}-industry`}>Industry
        <input id={`${id}-industry`} value={form.industry} maxLength={100} placeholder="e.g. FinTech" onChange={(e) => set("industry")(e.target.value)} />
      </label>

      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <Button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
        {onCancel && <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>}
        <Button variant="text" onClick={onDiscard} disabled={busy}>Discard resume</Button>
      </div>
    </Card>
  );
}
