// kind: skill (has it) | gap (missing) | done | assumed | plain. With `onRemove` it gets a ×
// button; `noted` shows that the removal is already queued.
export default function SkillBadge({ kind = "skill", onRemove, removeLabel, noted, children }) {
  return (
    <span className={`badge badge-${kind}${onRemove ? " badge-removable" : ""}${noted ? " badge-noted" : ""}`}>
      {children}
      {onRemove && (
        <button type="button" className="badge-remove" aria-label={removeLabel} disabled={noted} onClick={onRemove}>
          ×
        </button>
      )}
    </span>
  );
}
