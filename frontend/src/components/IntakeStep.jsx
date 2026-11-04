import { useState } from "react";
import { updateProfile } from "../api.js";
import { DEFAULT_PREFERENCES, ratedCount, CAPABILITY_AREAS } from "../capabilities.js";
import Button from "./Button.jsx";
import FilterChip from "./FilterChip.jsx";
import ResumeUpload from "./ResumeUpload.jsx";
import { CapabilityRatings, cleanConstraints, ConstraintsInput, PreferenceChips } from "./ProfileInputs.jsx";

// The answer widget under the chat for the current intake step. Widgets save through the
// profile API, then send a short chat message so the assistant moves to the next step.
export default function IntakeStep({ step, profile, resume, suggestions, onProfile, onResume, onSend }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [prefs, setPrefs] = useState(profile.learning_preferences ?? DEFAULT_PREFERENCES);
  const [constraints, setConstraints] = useState(profile.constraints ?? {});

  async function save(fields, message) {
    setBusy(true);
    setError("");
    try {
      onProfile(await updateProfile(fields));
      if (message) onSend(message);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const skip = (name, message) => save({ skip: [name] }, message);
  const errorText = error && <p className="error" role="alert">{error}</p>;

  if (step === "goal") {
    return suggestions.length ? (
      <div className="chips" role="group" aria-label="Suggested roles">
        {suggestions.map((s) => (
          <FilterChip key={s.role} onClick={() => onSend(s.role)}>
            <strong>{s.role}</strong>
            <small>{s.reason}</small>
          </FilterChip>
        ))}
      </div>
    ) : (
      <div className="chips">
        <FilterChip onClick={() => onSend("I'm not sure, help me choose")}>Help me choose</FilterChip>
      </div>
    );
  }

  if (step === "resume") {
    // After the upload the review screen opens (Intake); saving it moves the chat on.
    return (
      <>
        <ResumeUpload resume={resume} busy={busy} onUploaded={onResume} onSkip={() => skip("resume", "Skip the resume")} />
        {errorText}
      </>
    );
  }

  if (step === "capabilities") {
    const rated = ratedCount(profile.capabilities);
    const total = Object.keys(CAPABILITY_AREAS).length;
    return (
      <div className="widget">
        <CapabilityRatings value={profile.capabilities} disabled={busy}
          onRate={(area, level) => save({ capabilities: { [area]: level } })} />
        {errorText}
        <div className="row">
          <Button disabled={busy || rated < total} onClick={() => onSend("Done")}>Continue</Button>
          {rated < total && <span className="muted">{rated} of {total} rated</span>}
        </div>
      </div>
    );
  }

  if (step === "preferences") {
    return (
      <div className="widget">
        <PreferenceChips value={prefs} onChange={setPrefs} disabled={busy} />
        {errorText}
        <div className="row">
          <Button disabled={busy || prefs.length === 0} onClick={() => save({ learning_preferences: prefs }, "Done")}>Continue</Button>
          <Button variant="text" disabled={busy} onClick={() => skip("preferences", "Skip")}>Skip, use the defaults</Button>
        </div>
      </div>
    );
  }

  if (step === "constraints") {
    return (
      <div className="widget">
        <ConstraintsInput value={constraints} onChange={setConstraints} disabled={busy} />
        {errorText}
        <div className="row">
          <Button disabled={busy} onClick={() => save({ constraints: cleanConstraints(constraints) }, "Done")}>Continue</Button>
          <Button variant="text" disabled={busy} onClick={() => skip("constraints", "No constraints")}>No constraints</Button>
        </div>
      </div>
    );
  }

  if (step === "context") {
    return (
      <div className="widget">
        <p className="muted">Type anything you'd like to add, or skip.</p>
        {errorText}
        <div className="row">
          <Button variant="text" disabled={busy} onClick={() => skip("context", "Nothing to add")}>Nothing to add</Button>
        </div>
      </div>
    );
  }

  return null;
}
