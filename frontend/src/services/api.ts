// API client with guarded token refresh handling

type RequestConfig = RequestInit & { url: string };

let refreshPromise: Promise<boolean> | null = null;
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function refreshToken(): Promise<boolean> {
  const res = await fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
  });
  if (res.ok) {
    const data = await res.json();
    accessToken = data.accessToken ?? null;
    return true;
  }
  accessToken = null;
  return false;
}

async function guardedRefresh(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise;
  }
  refreshPromise = refreshToken().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

export async function apiFetch<T>(config: RequestConfig): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const headers = new Headers(config.headers);
    if (accessToken) {
      headers.set('Authorization', `Bearer ${accessToken}`);
    }
    return fetch(config.url, { ...config, headers });
  };

  let res = await doFetch();

  if (res.status === 401) {
    const refreshed = await guardedRefresh();
    if (refreshed) {
      res = await doFetch();
    }
  }

  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}
