import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';

import { endpoints } from '@/lib/api/endpoints';
import type { ApiResponse } from '@/lib/api/types';
import { clearAccessToken, getAccessToken, setAccessToken } from '@/lib/auth/token-store';
import { env } from '@/lib/env';
import { AppError, toAppError } from '@/lib/errors';

/**
 * Per-request options, including our interceptor control flags.
 *
 * Callers use this type; declaring the flags here means a screen can opt out of
 * the refresh flow without an unsafe cast.
 */
export interface RequestOptions extends AxiosRequestConfig {
  /**
   * Skip the transparent refresh-and-retry on a 401.
   *
   * Set it on requests where a 401 is a legitimate answer rather than an
   * expired token -- the session bootstrap call being the main example.
   */
  _skipAuthRefresh?: boolean;
}

/** Internal view of a config that has passed through the request interceptor. */
interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  /** Set once a request has already been retried after a token refresh. */
  _retried?: boolean;
  _skipAuthRefresh?: boolean;
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: env.NEXT_PUBLIC_API_BASE_URL,
  timeout: 20_000,
  // Required so the browser sends and stores the HttpOnly refresh cookie.
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Request: attach the access token
// ---------------------------------------------------------------------------
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

// ---------------------------------------------------------------------------
// Response: transparent single-flight token refresh
// ---------------------------------------------------------------------------

/**
 * The in-flight refresh, if any.
 *
 * When several requests 401 at once, they must not each fire their own refresh:
 * the backend rotates refresh tokens and treats a replayed one as theft, so
 * concurrent refreshes would revoke the user's entire session. Every waiter
 * therefore awaits this single shared promise.
 */
let refreshPromise: Promise<string> | null = null;

/** Callbacks invoked when the session cannot be recovered. */
const sessionExpiredHandlers = new Set<() => void>();

export function onSessionExpired(handler: () => void): () => void {
  sessionExpiredHandlers.add(handler);
  return () => {
    sessionExpiredHandlers.delete(handler);
  };
}

function notifySessionExpired(): void {
  clearAccessToken();
  for (const handler of sessionExpiredHandlers) {
    handler();
  }
}

async function refreshAccessToken(): Promise<string> {
  // A bare axios call, not `apiClient`: this request must bypass the response
  // interceptor, otherwise a failing refresh would recurse into itself.
  const response = await axios.post<ApiResponse<{ tokens: { access_token: string } }>>(
    `${env.NEXT_PUBLIC_API_BASE_URL}${endpoints.auth.refresh}`,
    {},
    { withCredentials: true, timeout: 20_000 },
  );

  const token = response.data.data?.tokens.access_token;
  if (!token) {
    throw new AppError('The session could not be renewed.', { status: 401, code: 'refresh_failed' });
  }

  setAccessToken(token);
  return token;
}

/** Start a refresh, or join the one already running. */
function requestRefresh(): Promise<string> {
  refreshPromise ??= refreshAccessToken().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

/**
 * Turn an error body that arrived as a Blob back into the parsed envelope.
 *
 * A request made with `responseType: 'blob'` — a download, a preview, an export
 * — gets that response type applied to the *error* body too. The envelope is
 * still JSON, but it reaches `toAppError` wrapped in a Blob, which does not
 * match the expected shape, so every such failure degrades to "Something went
 * wrong" and the server's actual message is lost. Unwrapping here fixes it once
 * for every caller rather than at each download site.
 */
async function unwrapBlobErrorBody(error: AxiosError): Promise<void> {
  const response = error.response;
  // `Blob` is browser-only; this module is also loaded during server rendering.
  if (!response || typeof Blob === 'undefined' || !(response.data instanceof Blob)) return;
  if (!response.data.type.includes('json')) return;

  try {
    response.data = JSON.parse(await response.data.text());
  } catch {
    // Not the envelope after all. The generic message is a better outcome than
    // throwing while already handling an error.
  }
}

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: unknown) => {
    if (!(error instanceof AxiosError)) {
      return Promise.reject(toAppError(error));
    }

    await unwrapBlobErrorBody(error);

    const config = error.config as RetryableRequestConfig | undefined;
    const status = error.response?.status;

    const canAttemptRefresh =
      status === 401 &&
      config !== undefined &&
      config._retried !== true &&
      config._skipAuthRefresh !== true &&
      // The auth endpoints below either establish or end a session; a 401 from
      // them is a genuine answer, not an expired access token.
      config.url !== endpoints.auth.login &&
      config.url !== endpoints.auth.refresh;

    if (!canAttemptRefresh) {
      if (status === 401 && config?._skipAuthRefresh !== true) {
        notifySessionExpired();
      }
      return Promise.reject(toAppError(error));
    }

    config._retried = true;

    try {
      const token = await requestRefresh();
      config.headers.set('Authorization', `Bearer ${token}`);
      return await apiClient.request(config);
    } catch (refreshError) {
      notifySessionExpired();
      return Promise.reject(toAppError(refreshError));
    }
  },
);

// ---------------------------------------------------------------------------
// Typed helpers
// ---------------------------------------------------------------------------

/**
 * Unwrap the standard envelope and return `data`.
 *
 * A 2xx response whose `data` is null when the caller expects a payload means
 * the contract was broken; surfacing that as an error beats letting `null`
 * propagate into the UI.
 */
function unwrap<TData>(response: AxiosResponse<ApiResponse<TData>>): TData {
  const body = response.data;
  if (body.data === null || body.data === undefined) {
    throw new AppError(body.message || 'The server returned an empty response.', {
      status: response.status,
      code: 'empty_response',
    });
  }
  return body.data;
}

export const api = {
  async get<TData>(url: string, config?: RequestOptions): Promise<TData> {
    return unwrap(await apiClient.get<ApiResponse<TData>>(url, config));
  },

  async post<TData>(url: string, body?: unknown, config?: RequestOptions): Promise<TData> {
    return unwrap(await apiClient.post<ApiResponse<TData>>(url, body, config));
  },

  async patch<TData>(url: string, body?: unknown, config?: RequestOptions): Promise<TData> {
    return unwrap(await apiClient.patch<ApiResponse<TData>>(url, body, config));
  },

  async put<TData>(url: string, body?: unknown, config?: RequestOptions): Promise<TData> {
    return unwrap(await apiClient.put<ApiResponse<TData>>(url, body, config));
  },

  async delete<TData>(url: string, config?: RequestOptions): Promise<TData> {
    return unwrap(await apiClient.delete<ApiResponse<TData>>(url, config));
  },

  /** Full envelope, for endpoints whose `message` matters more than `data`. */
  async postEnvelope<TData>(url: string, body?: unknown): Promise<ApiResponse<TData>> {
    const response = await apiClient.post<ApiResponse<TData>>(url, body);
    return response.data;
  },
};
