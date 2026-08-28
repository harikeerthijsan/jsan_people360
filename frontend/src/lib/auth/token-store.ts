/**
 * In-memory access token storage.
 *
 * Why not `localStorage`: anything readable by JavaScript is readable by an XSS
 * payload. Keeping the access token in a module-scoped variable means it dies
 * with the tab and never touches persistent storage.
 *
 * The *refresh* token lives in an HttpOnly cookie set by the backend, which the
 * browser attaches automatically and script cannot read. On a full page load the
 * app calls `/auth/refresh` once to mint a new access token from that cookie --
 * that is what makes the session survive a reload without persisting anything
 * sensitive on the client.
 */

let accessToken: string | null = null;

type Listener = (token: string | null) => void;
const listeners = new Set<Listener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
  for (const listener of listeners) {
    listener(token);
  }
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

/** Subscribe to token changes. Returns an unsubscribe function. */
export function onAccessTokenChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
