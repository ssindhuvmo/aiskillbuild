import { useRef, useState } from "react";
import { uploadResume } from "../api.js";
import Button from "./Button.jsx";
import Icon from "./Icon.jsx";
import Progress from "./Progress.jsx";

const MAX_BYTES = 5 * 1024 * 1024; // must match resume_parser/extract.py
const PARSING = [
  "Reading your resume…",
  "Finding your roles and dates…",
  "Picking out your skills and certifications…",
  "Checking everything against the text of your resume…",
  "Almost done — getting it ready for your review…",
];

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function resumeCounts(data) {
  return `${plural(data.roles.length, "role")}, ${plural(data.skills.length, "skill")}, ${plural(data.certifications.length, "certification")}`;
}

// Picks a PDF or DOCX and uploads it; the parsed draft opens for review (onUploaded(state)).
// `resume` is the current ResumeState, shown as a file card with Replace.
export default function ResumeUpload({ resume, onUploaded, onSkip, busy }) {
  const input = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function choose(e) {
    const file = e.target.files[0];
    e.target.value = ""; // choosing the same file again still fires onChange
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) return setError("Choose a PDF or DOCX file.");
    if (file.size > MAX_BYTES) return setError("The file is larger than 5 MB.");
    setError("");
    setUploading(true);
    try {
      onUploaded(await uploadResume(file));
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  if (uploading) return <Progress messages={PARSING} note="This usually takes 10–20 seconds." />;

  const has = resume && resume.status !== "none";
  return (
    <div className="widget">
      <p>Upload your resume and I'll read your roles, skills and certifications from it. You can check everything before it's saved.</p>
      <div className="file-card">
        <div className="file-card-info">
          <Icon name={has ? "fileDone" : "resume"} />
          <div>
            <div className="file-card-name">{has ? resume.filename : "No file chosen"}</div>
            {has && <div className="muted">Read: {resumeCounts(resume.data)}</div>}
          </div>
        </div>
        <input ref={input} type="file" accept=".pdf,.docx" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={choose} />
        <Button variant="secondary" disabled={busy} onClick={() => input.current.click()}>
          {has ? "Replace" : "Choose file"}
        </Button>
      </div>
      <p className="muted">PDF or DOCX, up to 5 MB. No resume? Skip this and answer a few questions instead.</p>
      {error && <p className="error" role="alert">{error}</p>}
      {onSkip && (
        <div className="row">
          <Button variant="text" disabled={busy} onClick={onSkip}>Skip</Button>
        </div>
      )}
    </div>
  );
}
