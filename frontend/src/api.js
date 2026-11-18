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
      detail = typeof d === "string" ? d : d?.errors ? [...new Set(Object.values(d.errors))].join(" ") : "";
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
export const startOver = () => request("/api/account/data", { method: "DELETE" });

export const getIntake = () => request("/api/intake");
export const getDomains = () => request("/api/domains");
export const updateProfile = (fields) => request("/api/profile", json("PUT", fields));
export const confirmProfile = () => request("/api/profile/confirm", json("POST"));

export const getResume = () => request("/api/resume");
// FormData sets its own multipart Content-Type, so no JSON header here.
export function uploadResume(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/api/resume", { method: "POST", body });
}
export const saveResume = (data) => request("/api/resume", json("PUT", data));
export const deleteResume = () => request("/api/resume", { method: "DELETE" });

export const getGaps = () => request("/api/gaps");
export const analyzeGaps = (corrections) => request("/api/gaps/analyze", json("POST", { corrections }));
export const confirmGaps = () => request("/api/gaps/confirm", json("POST"));
// One Skill Analysis button (knows | not_needed | later | plan | restore); `make_room` accepts a budget suggestion.
export const adjustGap = (action, skill, make_room = []) =>
  request("/api/gaps/adjust", json("POST", { action, skill, make_room }));

export const getResources = () => request("/api/resources");
export const searchResources = () => request("/api/resources/search", json("POST"));
export const removeResource = (resource_id) => request("/api/resources/remove", json("POST", { resource_id }));
export const approveResources = () => request("/api/resources/approve", json("POST"));
// The filter chips: {cost: "any" | "free" | "paid", levels: [...], types: [...]}; [] means no filter.
export const filterResources = (filters) => request("/api/resources/filter", json("POST", filters));
// Save / Start / Complete on one resource: change is {saved} and/or {status}.
export const setResourceProgress = (resource_id, change) =>
  request("/api/resources/progress", json("PUT", { resource_id, ...change }));

export const getRoadmap = () => request("/api/roadmap");

export const setStartDate = (start_date) => request("/api/roadmap/start-date", json("PUT", { start_date }));
export const setRoadmapItem = (item_id, done) => request("/api/roadmap/items", json("PUT", { item_id, done }));

// Fetches an export and saves it as a file.
async function download(path, filename) {
  const res = await fetch(path);
  if (res.status === 401) onUnauthorized();
  if (!res.ok) throw new Error(`Download failed (${res.status}).`);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

// format: "md" | "pdf"
export const downloadRoadmap = (format = "md") => download(`/api/roadmap/export.${format}`, `ai-career-roadmap.${format}`);

export const getReport = () => request("/api/report");
export const generateReport = () => request("/api/report/generate", json("POST"));
export const downloadReport = (format) =>
  download(`/api/report/export.${format}`, `ai-career-transition-report.${format}`);

// Posts to an SSE endpoint and calls onEvent(event) for each `data:` frame; failures go to onError(msg).
async function streamEvents(path, body, onEvent, onError) {
  let res;
  try {
    res = await fetch(path, json("POST", body));
  } catch {
    onError("Cannot reach the server. Is the backend running on port 8000?");
    return;
  }
  if (res.status === 401) {
    onUnauthorized();
    return;
  }
  if (!res.ok || !res.body) {
    let detail = "";
    try {
      detail = (await res.json()).detail;
    } catch {}
    onError(typeof detail === "string" && detail ? detail : `Request failed (${res.status}).`);
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
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}

// Streams a chat reply over SSE from /api/intake/chat or /api/resources/chat.
// Handlers: onToken(text), onState(event: {profile} or {resources}), onError(msg).
export function streamChat(path, message, { onToken, onState, onError }) {
  return streamEvents(path, { message }, (evt) => {
    if (evt.type === "token") onToken(evt.text);
    else if (evt.type === "state") onState(evt);
    else if (evt.type === "error") onError(evt.message);
  }, onError);
}

// Builds the roadmap: onState({state, phase, notice}) first with the placed plan (every phase "pending"),
// then once per phase as its text arrives. Resolves when the stream ends.
export function generateRoadmap({ onState, onError }) {
  return streamEvents("/api/roadmap/generate", undefined, (evt) => {
    if (evt.type === "state" && evt.state) onState(evt);
    else if (evt.type === "error") onError(evt.message);
  }, onError);
}

// Dashboard and Progress Review (milestone 11). Every number comes from the backend.
export const getDashboard = () => request("/api/dashboard");
export const recalcReadiness = () => request("/api/dashboard/readiness", json("POST"));
export const getProgressReview = () => request("/api/progress");
export const saveProgressReview = (skills, notes) => request("/api/progress", json("PUT", { skills, notes }));

// Refresh my plan: keeps the done work and replans the remaining weeks. Same events as generateRoadmap; the
// first state event also carries `from_week`.
export function refreshRoadmap({ onState, onError }) {
  return streamEvents("/api/roadmap/refresh", undefined, (evt) => {
    if (evt.type === "state" && evt.state) onState(evt);
    else if (evt.type === "error") onError(evt.message);
  }, onError);
}

// Job Match (milestone 12). Scores, salaries and links all come from the backend.
export const getJobs = () => request("/api/jobs");
export const searchJobs = (query) => request("/api/jobs/search", json("POST", query));
export const markJob = (job_id, change) => request("/api/jobs/marks", json("PUT", { job_id, ...change }));

// Feedback form: { rating (1-5 or null), areas ([] = the whole platform), message }.
export const sendFeedback = (feedback) => request("/api/feedback", json("POST", feedback));
