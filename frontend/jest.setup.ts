import '@testing-library/jest-dom';

// The public environment is validated at import time, so the test process must
// provide it before any application module loads.
process.env['NEXT_PUBLIC_API_BASE_URL'] ??= 'http://localhost:8000/api/v1';
process.env['NEXT_PUBLIC_APP_NAME'] ??= 'JSAN People360';
process.env['NEXT_PUBLIC_APP_ENV'] ??= 'local';

// jsdom implements neither of these, and Radix primitives call both.
if (typeof window !== 'undefined') {
  window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })) as unknown as typeof window.matchMedia;

  window.ResizeObserver ??= class {
    observe(): void {
      /* no-op */
    }
    unobserve(): void {
      /* no-op */
    }
    disconnect(): void {
      /* no-op */
    }
  } as unknown as typeof window.ResizeObserver;

  // Radix's Select uses the Pointer Capture API and scrolls the active item
  // into view when it opens. jsdom implements neither, so without these a
  // select simply never opens and any test that drives one fails for a reason
  // that has nothing to do with the component under test.
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => undefined;
  Element.prototype.releasePointerCapture ??= () => undefined;
  Element.prototype.scrollIntoView ??= () => undefined;
}

// This jsdom ships `Blob` without `Blob.prototype.text`, which every browser the
// app targets has had for years. The API client uses it to recover the error
// envelope from a failed blob request, so without this the code under test takes
// its fallback path and a test would pass for the wrong reason.
if (typeof Blob !== 'undefined' && typeof Blob.prototype.text !== 'function') {
  Blob.prototype.text = function text(this: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        resolve(String(reader.result));
      };
      reader.onerror = () => {
        reject(reader.error ?? new Error('Could not read the blob.'));
      };
      reader.readAsText(this);
    });
  };
}
