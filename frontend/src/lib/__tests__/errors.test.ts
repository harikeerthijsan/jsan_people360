import { AxiosError, AxiosHeaders } from 'axios';

import type { ApiResponse } from '@/lib/api/types';
import { AppError, getErrorMessage, toAppError } from '@/lib/errors';

function axiosErrorWithResponse(status: number, data: unknown): AxiosError {
  const error = new AxiosError('Request failed');
  const headers = new AxiosHeaders();
  error.config = { headers };
  error.response = {
    status,
    statusText: '',
    data,
    headers,
    config: { headers },
  };
  return error;
}

const validationEnvelope: ApiResponse<null> = {
  success: false,
  message: 'One or more fields failed validation.',
  data: null,
  errors: [
    { code: 'value_error', message: 'Enter a valid email address', field: 'email' },
    { code: 'value_error', message: 'Password is required', field: 'password' },
  ],
};

describe('toAppError', () => {
  it('reads message and field errors from the API envelope', () => {
    const result = toAppError(axiosErrorWithResponse(422, validationEnvelope));

    expect(result).toBeInstanceOf(AppError);
    expect(result.message).toBe('One or more fields failed validation.');
    expect(result.status).toBe(422);
    expect(result.fieldErrors).toHaveLength(2);
    expect(result.isValidationError).toBe(true);
  });

  it('maps field errors to a record keyed by field name', () => {
    const result = toAppError(axiosErrorWithResponse(422, validationEnvelope));

    expect(result.fieldErrorMap).toEqual({
      email: 'Enter a valid email address',
      password: 'Password is required',
    });
  });

  it('flags 401 responses as unauthorized', () => {
    const result = toAppError(
      axiosErrorWithResponse(401, {
        success: false,
        message: 'Incorrect email or password.',
        data: null,
        errors: [{ code: 'invalid_credentials', message: 'Incorrect email or password.', field: null }],
      }),
    );

    expect(result.isUnauthorized).toBe(true);
    expect(result.code).toBe('invalid_credentials');
  });

  it('does not leak a non-envelope response body', () => {
    const result = toAppError(axiosErrorWithResponse(500, '<html>Internal Server Error stack trace</html>'));

    expect(result.message).toBe('Something went wrong. Please try again.');
    expect(result.message).not.toContain('stack trace');
  });

  it('reports a request that never reached the server as a network error', () => {
    const error = new AxiosError('Network Error');
    error.config = { headers: new AxiosHeaders() };

    const result = toAppError(error);

    expect(result.isNetworkError).toBe(true);
    expect(result.status).toBeNull();
    expect(result.message).toContain('Cannot reach the server');
  });

  it('distinguishes a timeout from a connection failure', () => {
    const error = new AxiosError('timeout of 20000ms exceeded');
    error.code = 'ECONNABORTED';
    error.config = { headers: new AxiosHeaders() };

    expect(toAppError(error).code).toBe('timeout');
  });

  it('passes an existing AppError through unchanged', () => {
    const original = new AppError('Already normalised', { status: 418, code: 'teapot' });
    expect(toAppError(original)).toBe(original);
  });

  it('wraps a plain Error', () => {
    expect(toAppError(new Error('Boom')).message).toBe('Boom');
  });

  it('falls back for a thrown non-Error value', () => {
    expect(toAppError('just a string').message).toBe('Something went wrong. Please try again.');
  });
});

describe('getErrorMessage', () => {
  it('returns a user-presentable message for any input', () => {
    expect(getErrorMessage(new Error('Something specific'))).toBe('Something specific');
    expect(getErrorMessage(null)).toBe('Something went wrong. Please try again.');
  });
});
