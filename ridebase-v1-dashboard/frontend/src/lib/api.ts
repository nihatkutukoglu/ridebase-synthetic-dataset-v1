"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

export async function apiGet<T = unknown>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, (body as { detail?: unknown }).detail ?? body);
  return body as T;
}

export async function apiPost<T = unknown>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, (body as { detail?: unknown }).detail ?? body);
  return body as T;
}

type State<T> = { data: T | null; loading: boolean; error: ApiError | Error | null };

/** Tiny data hook — loading / error / empty states, no external dep. */
export function useApi<T = unknown>(path: string | null, deps: unknown[] = []): State<T> & {
  reload: () => void;
} {
  const [state, setState] = useState<State<T>>({ data: null, loading: !!path, error: null });
  const tick = useRef(0);

  const run = useCallback(() => {
    if (!path) return;
    const id = ++tick.current;
    const ctrl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    apiGet<T>(path, ctrl.signal)
      .then((data) => id === tick.current && setState({ data, loading: false, error: null }))
      .catch((error) => {
        if (ctrl.signal.aborted || id !== tick.current) return;
        setState({ data: null, loading: false, error });
      });
    return () => ctrl.abort();
  }, [path]);

  useEffect(() => {
    const cleanup = run();
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, ...deps]);

  return { ...state, reload: run };
}
