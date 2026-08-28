import nextJest from 'next/jest.js';

// `next/jest` wires up SWC transforms, CSS module stubs, the `@/` alias and
// `.env` loading, so the test environment matches the build.
//
// This file is ESM rather than TypeScript on purpose: a `jest.config.ts` would
// drag in `ts-node` purely to read the config.
const createJestConfig = nextJest({ dir: './' });

/** @type {import('jest').Config} */
const config = {
  testEnvironment: 'jest-environment-jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],

  testPathIgnorePatterns: ['<rootDir>/.next/', '<rootDir>/node_modules/'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },

  collectCoverageFrom: [
    'src/**/*.{ts,tsx}',
    '!src/**/*.d.ts',
    '!src/app/**/layout.tsx',
    '!src/app/**/loading.tsx',
    '!src/**/index.ts',
  ],
  coverageThreshold: {
    // A deliberately modest floor for Phase 1: high enough to stop coverage
    // regressing, low enough not to encourage tests written for the metric.
    global: { statements: 25, branches: 25, functions: 25, lines: 25 },
  },

  clearMocks: true,
  restoreMocks: true,
};

export default createJestConfig(config);
