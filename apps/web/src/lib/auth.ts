type TokenPayload = {
  exp?: number;
};

function decodePayload(token: string): TokenPayload | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64)) as TokenPayload;
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token") || localStorage.getItem("token");
}

export function storeTokens(tokens: { access_token: string; refresh_token?: string }) {
  localStorage.setItem("access_token", tokens.access_token);
  if (tokens.refresh_token) {
    localStorage.setItem("refresh_token", tokens.refresh_token);
  }
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("token");
}

/** Return a usable access token, refreshing it shortly before it expires. */
export async function ensureAccessToken(): Promise<string | null> {
  const accessToken = getAccessToken();
  const payload = accessToken ? decodePayload(accessToken) : null;
  const now = Math.floor(Date.now() / 1000);

  if (accessToken && payload?.exp && payload.exp > now + 30) {
    return accessToken;
  }

  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return accessToken;

  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    clearTokens();
    return null;
  }

  const body = await response.json();
  const tokens = body?.data?.tokens;
  if (!tokens?.access_token) {
    clearTokens();
    return null;
  }

  storeTokens(tokens);
  return tokens.access_token;
}
