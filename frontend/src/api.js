async function request(path, options) {
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new Error("Cannot reach the server. Is the backend running on port 8000?");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      const d = body.detail;
      detail = typeof d === "string" ? d : d?.errors ? Object.values(d.errors).join(" ") : "";
    } catch {}
    throw new Error(detail || `Request failed (${res.status}).`);
  }
  return res.json();
}

const u = (id) => `/api/users/${encodeURIComponent(id)}`;
const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body ? JSON.stringify(body) : undefined,
});

export const getIntake = (id) => request(`${u(id)}/intake`);
export const getDomains = () => request("/api/domains");
export const updateProfile = (id, fields) => request(`${u(id)}/profile`, json("PUT", fields));
export const confirmProfile = (id) => request(`${u(id)}/profile/confirm`, json("POST"));

// Streams the reply over SSE. Handlers: onToken(text), onState(profile), onError(msg).
export async function streamChat(id, message, { onToken, onState, onError }) {
  let res;
  try {
    res = await fetch(`${u(id)}/intake/chat`, json("POST", { message }));
  } catch {
    onError("Cannot reach the server. Is the backend running on port 8000?");
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
