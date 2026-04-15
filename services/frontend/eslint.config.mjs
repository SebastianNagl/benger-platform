// Import eslint-config-next flat config (16.x)
// Using CommonJS require since the package exports CommonJS
import { createRequire } from 'module'
const require = createRequire(import.meta.url)

const nextConfig = require('eslint-config-next/core-web-vitals')

const eslintConfig = [
  ...nextConfig,
  {
    ignores: [
      '.next/**',
      'out/**',
      'build/**',
      'node_modules/**',
      'coverage/**',
      'playwright-report/**',
    ],
  },
  {
    rules: {
      // Custom overrides
      'react/no-unescaped-entities': 'off',

      // React Hooks 7.x React Compiler rules - all violations fixed
      // Keep exhaustive-deps as warning (some patterns are intentional, with eslint-disable comments)
      'react-hooks/exhaustive-deps': 'warn',
      // Keep no-img-element as warning (dynamic/external images use eslint-disable)
      '@next/next/no-img-element': 'warn',

      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'vitest',
              message: 'Please use Jest instead of Vitest. This project uses Jest for all testing.',
            },
          ],
          patterns: [
            {
              group: ['vitest', 'vitest/*'],
              message: 'Vitest is not allowed. Use Jest for testing (jest.fn(), jest.mock(), etc.)',
            },
          ],
        },
      ],
    },
  },
]

export default eslintConfig
