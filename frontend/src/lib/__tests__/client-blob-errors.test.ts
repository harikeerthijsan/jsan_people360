import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios';

import { apiClient } from '@/lib/api/client';
import { AppError } from '@/lib/errors';

/**
 * A failed request made with `responseType: 'blob'` must still surface the
 * server's message.
 *
 * Downloads, previews and exports all ask axios for a Blob, and axios applies
 * that response type to the *error* body too. The envelope is still JSON, so
 * without unwrapping it the message never reaches `toAppError` and every such
 * failure reads "Something went wrong" — hiding the one sentence that tells the
 * user what to do.
 */

const ENVELOPE = {
  success: false,
  message: 'The stored file for this document could not be found.',
  data: null,
  errors: [{ code: 'not_found', message: 'The stored file could not be found.', field: null }],
};

/** Reject the way axios does for a non-2xx with `responseType: 'blob'`. */
function rejectWithBlob(body: unknown, type = 'application/json'): void {
  const config = {
    headers: new AxiosHeaders(),
    responseType: 'blob',
    url: '/documents/x/download',
  } as InternalAxiosRequestConfig;

  apiClient.defaults.adapter = () =>
    Promise.reject(
      new AxiosError('Request failed with status code 404', 'ERR_BAD_REQUEST', config, null, {
        status: 404,
        statusText: 'Not Found',
        headers: new AxiosHeaders(),
        config,
        data: new Blob([typeof body === 'string' ? body : JSON.stringify(body)], { type }),
      }),
    );
}

describe('blob error bodies', () => {
  afterEach(() => {
    delete apiClient.defaults.adapter;
  });

  it("keeps the server's message when the error body arrived as a Blob", async () => {
    rejectWithBlob(ENVELOPE);

    await expect(apiClient.get('/documents/x/download', { responseType: 'blob' })).rejects.toMatchObject({
      message: ENVELOPE.message,
      status: 404,
      code: 'not_found',
    });
  });

  it('falls back to the generic message when the blob is not the envelope', async () => {
    rejectWithBlob('<html>a proxy error page</html>', 'text/html');

    const error = await apiClient
      .get('/documents/x/download', { responseType: 'blob' })
      .catch((caught: AppError) => caught);

    expect(error).toBeInstanceOf(AppError);
    expect((error as AppError).message).not.toContain('<html>');
  });
});
