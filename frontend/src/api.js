// Called on any 401 so the app can drop back to the sign-in screen (e.g. session expired).
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

async function request(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the server. Is the backend running on port 8000?");
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) onUnauthorized();
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      const d = body.detail;
      detail = typeof d === "string" ? d : d?.errors ? Object.values(d.errors).join(" ") : "";
    } catch {}
    throw Object.assign(new Error(detail || `Request failed (${res.status}).`), { status: res.status });
  }
  return res.json();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body ? JSON.stringify(body) : undefined,
});

// The session cookie is httpOnly and same-origin (Vite proxies /api), so fetch sends it
// automatically; no user ID is ever passed from the browser.
export const getMe = () => request("/api/auth/me");
export const googleLogin = (credential) => request("/api/auth/google", json("POST", { credential }));
export const logout = () => request("/api/auth/logout", json("POST"));

export const getIntake = () => request("/api/intake");
export const getDomains = () => request("/api/domains");
export const updateProfile = (fields) => request("/api/profile", json("PUT", fields));
export const confirmProfile = () => request("/api/profile/confirm", json("POST"));

export const getGaps = () => request("/api/gaps");
export const analyzeGaps = (corrections) => request("/api/gaps/analyze", json("POST", { corrections }));
export const confirmGaps = () => request("/api/gaps/confirm", json("POST"));

export const getResources = () => request("/api/resources");
export const searchResources = () => request("/api/resources/search", json("POST"));

// Streams the reply over SSE. Handlers: onToken(text), onState(profile), onError(msg).
export async function streamChat(message, { onToken, onState, onError }) {
  let res;
  try {
    res = await fetch("/api/intake/chat", json("POST", { message }));
  } catch {
    onError("Cannot reach the server. Is the backend running on port 8000?");
    return;
  }
  if (res.status === 401) {
    onUnauthorized();
    return;
  }
  if (!res.ok || !res.body) {
    onError(`Request failed (${res.status}).`);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop();
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const evt = JSON.parse(line.slice(6));
      if (evt.type === "token") onToken(evt.text);
      else if (evt.type === "state") onState(evt.profile);
      else if (evt.type === "error") onError(evt.message);
    }
  }
}
