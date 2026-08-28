'use client';

import * as React from 'react';

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Last-resort boundary for failures in the root layout itself.
 *
 * Because the root layout is what failed, this component must supply its own
 * `<html>` and `<body>` and cannot rely on the design system or global CSS --
 * hence the inline styles.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps): React.JSX.Element {
  React.useEffect(() => {
    console.error('Fatal application error:', error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
          backgroundColor: '#ffffff',
          color: '#1e293b',
        }}
      >
        <main style={{ maxWidth: '28rem', padding: '2rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            The application could not start
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#64748b', marginBottom: '1.5rem' }}>
            A critical error prevented the interface from loading. Reload the page, and contact your
            administrator if this continues.
          </p>

          {error.digest ? (
            <p style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '1.5rem' }}>
              Reference: <code>{error.digest}</code>
            </p>
          ) : null}

          <button
            type="button"
            onClick={reset}
            style={{
              cursor: 'pointer',
              borderRadius: '0.375rem',
              border: 'none',
              backgroundColor: '#2563eb',
              padding: '0.5rem 1.25rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              color: '#ffffff',
            }}
          >
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
