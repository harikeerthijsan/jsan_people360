import { z } from 'zod';

/**
 * Validated public environment.
 *
 * Next.js inlines `NEXT_PUBLIC_*` values at build time, so they must be read as
 * complete literals (`process.env.NEXT_PUBLIC_API_BASE_URL`), never via a
 * computed key. Parsing them through Zod turns a missing or malformed variable
 * into a loud failure at startup instead of an `undefined` that surfaces as a
 * confusing runtime error much later.
 */
const publicEnvSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z
    .string()
    .url('NEXT_PUBLIC_API_BASE_URL must be a valid absolute URL')
    .default('http://localhost:8000/api/v1'),
  NEXT_PUBLIC_APP_NAME: z.string().min(1).default('JSAN People360'),
  NEXT_PUBLIC_APP_ENV: z.enum(['local', 'development', 'staging', 'production']).default('local'),
});

const parsed = publicEnvSchema.safeParse({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
});

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((issue) => `  - ${issue.path.join('.')}: ${issue.message}`)
    .join('\n');
  throw new Error(`Invalid public environment configuration:\n${issues}`);
}

export const env = Object.freeze(parsed.data);

export type PublicEnv = typeof env;

/** True in the deployed production environment (not merely a production build). */
export const isProduction = env.NEXT_PUBLIC_APP_ENV === 'production';
