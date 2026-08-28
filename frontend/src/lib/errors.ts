import { AxiosError } from 'axios';

import type { ApiErrorDetail, ApiResponse } from '@/lib/api/types';

/**
 * A normalised application error.
 *
 * Every failure the UI can encounter -- an API envelope, a network timeout, a
 * thrown `Error` -- is converted into this shape, so components render errors
 * one way instead of branching on error provenance.
 */
export class AppError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly fieldErrors: ApiErrorDetail[];

  constructor(
    message: string,
    options: { status?: number | null; code?: string; fieldErrors?: ApiErrorDetail[] } = {},
  ) {
    super(message);
    this.name = 'AppError';
    this.status = options.status ?? null;
    this.code = options.code ?? 'unknown_error';
    this.fieldErrors = options.fieldErrors ?? [];
  }

  /** True when the caller must sign in again. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  /** True when the request never reached the server. */
  get isNetworkError(): boolean {
    return this.code === 'network_error';
  }

  /** True when the server rejected the payload with field-level detail. */
  get isValidationError(): boolean {
    return this.status === 422 || this.code === 'validation_error';
  }

  /**
   * Field errors keyed by field name, ready to hand to
   * `react-hook-form`'s `setError`.
   */
  get fieldErrorMap(): Record<string, string> {
    const map: Record<string, string> = {};
    for (const detail of this.fieldErrors) {
      if (detail.field && !map[detail.field]) {
        map[detail.field] = detail.message;
      }
    }
    return map;
  }
}

const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';

const NETWORK_MESSAGE = 'Cannot reach the server. Check your connection and confirm the API is running.';

/** Type guard for the standard API envelope. */
function isApiResponse(value: unknown): value is ApiResponse<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'success' in value &&
    'message' in value &&
    typeof (value as { message: unknown }).message === 'string'
  );
}

/**
 * Convert any thrown value into an {@link AppError}.
 *
 * The backend always sends `{ success, message, data, errors }`, so its
 * `message` is written to be shown to a user directly. Anything that is not
 * that envelope falls back to a generic message rather than leaking internals.
 */
export function toAppError(error: unknown): AppError {
  if (error instanceof AppError) {
    return error;
  }

  if (error instanceof AxiosError) {
    if (error.response) {
      const body: unknown = error.response.data;

      if (isApiResponse(body)) {
        const details = body.errors ?? [];
        return new AppError(body.message || FALLBACK_MESSAGE, {
          status: error.response.status,
          code: details[0]?.code ?? 'api_error',
          fieldErrors: details,
        });
      }

      return new AppError(FALLBACK_MESSAGE, {
        status: error.response.status,
        code: 'api_error',
      });
    }

    // No response at all: DNS failure, connection refused, CORS, or timeout.
    return new AppError(NETWORK_MESSAGE, {
      status: null,
      code: error.code === 'ECONNABORTED' ? 'timeout' : 'network_error',
    });
  }

  if (error instanceof Error) {
    return new AppError(error.message || FALLBACK_MESSAGE, { code: 'client_error' });
  }

  return new AppError(FALLBACK_MESSAGE);
}

/** Extract a message that is safe and useful to show to a user. */
export function getErrorMessage(error: unknown): string {
  return toAppError(error).message;
}
