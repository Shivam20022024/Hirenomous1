/**
 * Candidate interview-session API client.
 *
 * Deliberately separate from `lib/api.ts`: the candidate flow authenticates ONLY
 * with the opaque interview token in the URL. It must never read or send the
 * recruiter JWT from localStorage.
 */
import { API_BASE_URL } from '@/lib/api';

function extFor(blob: Blob): string {
  const t = blob.type || '';
  if (t.includes('mp4')) return '.mp4';
  if (t.includes('ogg')) return '.ogg';
  if (t.includes('wav')) return '.wav';
  return '.webm';
}

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    // Skip ngrok's free-tier browser-warning page so responses are JSON, not
    // HTML (ignored on any other host, including Cloudflare Tunnel / prod).
    headers: { 'ngrok-skip-browser-warning': 'true', ...(options.headers as Record<string, string>) },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      detail = data?.detail || detail;
    } catch {}
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.blob();
}

export const interviewApi = {
  getSession: (token: string) =>
    request(`/interview-session/${encodeURIComponent(token)}`),

  start: (token: string) =>
    request(`/interview-session/${encodeURIComponent(token)}/start`, { method: 'POST' }),

  /**
   * Submit an answer. Video interview sends both `video` (for review) and a small
   * `audio` clip (for STT); text is the accessibility fallback.
   */
  turn: (
    token: string,
    opts: { video?: Blob; audio?: Blob; answerText?: string; turnSeq?: number; durationSeconds?: number },
  ) => {
    const form = new FormData();
    if (opts.video) form.append('video', opts.video, `answer${extFor(opts.video)}`);
    if (opts.audio) form.append('audio', opts.audio, `answer-audio${extFor(opts.audio)}`);
    if (opts.answerText) form.append('answer_text', opts.answerText);
    if (opts.turnSeq != null) form.append('turn_seq', String(opts.turnSeq));
    if (opts.durationSeconds != null) form.append('duration_seconds', String(Math.round(opts.durationSeconds)));
    return request(`/interview-session/${encodeURIComponent(token)}/turn`, {
      method: 'POST',
      body: form,
    });
  },

  complete: (token: string) =>
    request(`/interview-session/${encodeURIComponent(token)}/complete`, { method: 'POST' }),

  audioUrl: (token: string, filename: string) =>
    `${API_BASE_URL}/interview-session/${encodeURIComponent(token)}/audio/${encodeURIComponent(filename)}`,
};
