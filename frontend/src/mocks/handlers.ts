import { http, HttpResponse } from "msw";
import { API_BASE } from "../services/api";

/** Preview handlers are opt-in test fixtures, never a production fallback. */
export const previewHandlers = [
  http.get(`${API_BASE}/health/live`, () => HttpResponse.json({ status: "ok" })),
  http.get(`${API_BASE}/data-sources`, () => HttpResponse.json([])),
  http.get(`${API_BASE}/knowledge-bases`, () => HttpResponse.json([])),
];
