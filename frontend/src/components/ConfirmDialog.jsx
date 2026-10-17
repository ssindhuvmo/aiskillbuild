import { useEffect } from "react";
import Button from "./Button.jsx";

// A modal question with a destructive confirm button. Escape cancels.
export default function ConfirmDialog({ title, children, confirmLabel, busyLabel, busy, error, onCancel, onConfirm }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <div className="overlay">
      <div className="card dialog" role="alertdialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title">{title}</h2>
        {children}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <Button variant="secondary" onClick={onCancel} disabled={busy} autoFocus>Cancel</Button>
          <Button variant="danger" onClick={onConfirm} disabled={busy}>{busy ? busyLabel : confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
