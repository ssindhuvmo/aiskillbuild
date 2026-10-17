import { useEffect, useRef, useState } from "react";

const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const GIS_SRC = "https://accounts.google.com/gsi/client";

let gisPromise;
// Loads Google Identity Services once per page.
export function loadGis() {
  if (window.google?.accounts?.id) return Promise.resolve(window.google);
  gisPromise ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = GIS_SRC;
    s.async = true;
    s.onload = () => resolve(window.google);
    s.onerror = () => {
      gisPromise = undefined;
      reject(new Error("Could not load Google Sign-In. Check your connection and reload."));
    };
    document.head.appendChild(s);
  });
  return gisPromise;
}

// Renders the official "Sign in with Google" button; onCredential gets the ID token.
export default function GoogleSignIn({ onCredential }) {
  const el = useRef(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!CLIENT_ID) {
      setError("VITE_GOOGLE_CLIENT_ID is not set in frontend/.env.");
      return;
    }
    let cancelled = false;
    loadGis()
      .then((google) => {
        if (cancelled || !el.current) return;
        google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (resp) => onCredential(resp.credential),
        });
        google.accounts.id.renderButton(el.current, { theme: "filled_black", size: "large", text: "signin_with" });
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [onCredential]);

  return (
    <>
      <div ref={el} className="gsi-button" />
      {error && <p className="error" role="alert">{error}</p>}
    </>
  );
}
