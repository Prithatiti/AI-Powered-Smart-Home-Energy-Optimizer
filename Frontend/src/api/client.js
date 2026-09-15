const BASE = "";

async function request(path, options) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        detail = Array.isArray(data.detail)
          ? data.detail.map((d) => d.msg).join("; ")
          : data.detail;
      }
    } catch {
      /* keep default detail */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const fetchHealth = () =>
  request("/health", { method: "GET" });

export const fetchHistory = (limit = 200) =>
  request(`/api/v1/energy/history?limit=${limit}`, { method: "GET" });

export const postForecast = (profile) =>
  request("/api/v1/energy/forecast", {
    method: "POST",
    body: JSON.stringify(profile),
  });

export const postRecommendations = (payload) =>
  request("/api/v1/recommendations", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const postEmailPlan = (payload) =>
  request("/api/v1/email/plan", {
    method: "POST",
    body: JSON.stringify(payload),
  });