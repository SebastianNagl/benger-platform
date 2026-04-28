/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    // Extended-edition components are mounted into the build via Docker
    // (next.config.js maps `@benger/extended` to either
    // `/app/node_modules/@benger/extended` in CI builds or
    // `/app/benger-extended-frontend` in dev). Without these globs the
    // JIT silently drops any Tailwind class only referenced by extended
    // (e.g. `w-[96vw]` on the Klausurlösung modals → half-width modal).
    './node_modules/@benger/extended/**/*.{js,ts,jsx,tsx,mdx}',
    '../../benger-extended/frontend/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: ['class'],
  theme: {
    extend: {
      screens: {
        '3xl': '1600px',
        '4xl': '1920px',
        '5xl': '2560px',
      },
      fontSize: {
        '2xs': ['0.75rem', { lineHeight: '1.25rem' }],
        xs: ['0.8125rem', { lineHeight: '1.5rem' }],
        sm: ['0.875rem', { lineHeight: '1.5rem' }],
        base: ['1rem', { lineHeight: '1.75rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem' }],
      },
      lineHeight: {
        7: '1.75rem',
      },
      boxShadow: {
        glow: '0 0 4px rgb(0 0 0 / 0.1)',
      },
      maxWidth: {
        lg: '33rem',
        '3xl': '50rem',
        '5xl': '66rem',
        '6xl': '75rem',
        '7xl': '85rem',
        '8xl': '96rem',
        '9xl': '120rem',
      },
      container: {
        lg: '33rem',
        '2xl': '40rem',
        '3xl': '50rem',
        '5xl': '66rem',
        '6xl': '75rem',
        '7xl': '85rem',
        '8xl': '96rem',
      },
      typography: (theme) => ({
        DEFAULT: {
          css: {
            maxWidth: 'none',
            // Base typography matching protocol-ts
            fontSize: theme('fontSize.sm')[0],
            lineHeight: theme('lineHeight.7'),
            color: theme('colors.zinc.700'),

            // Prose styling
            '--tw-prose-body': theme('colors.zinc.700'),
            '--tw-prose-headings': theme('colors.zinc.900'),
            '--tw-prose-links': theme('colors.emerald.500'),
            '--tw-prose-links-hover': theme('colors.emerald.600'),
            '--tw-prose-links-underline': theme('colors.emerald.500 / 0.3'),
            '--tw-prose-bold': theme('colors.zinc.900'),
            '--tw-prose-counters': theme('colors.zinc.500'),
            '--tw-prose-bullets': theme('colors.zinc.300'),
            '--tw-prose-hr': theme('colors.zinc.900 / 0.05'),
            '--tw-prose-quotes': theme('colors.zinc.900'),
            '--tw-prose-quote-borders': theme('colors.zinc.200'),
            '--tw-prose-captions': theme('colors.zinc.500'),
            '--tw-prose-code': theme('colors.zinc.900'),
            '--tw-prose-code-bg': theme('colors.zinc.100'),
            '--tw-prose-code-ring': theme('colors.zinc.300'),
            '--tw-prose-th-borders': theme('colors.zinc.300'),
            '--tw-prose-td-borders': theme('colors.zinc.200'),

            // Dark mode variables - improved contrast
            '--tw-prose-invert-body': theme('colors.zinc.300'),
            '--tw-prose-invert-headings': theme('colors.white'),
            '--tw-prose-invert-links': theme('colors.emerald.400'),
            '--tw-prose-invert-links-hover': theme('colors.emerald.500'),
            '--tw-prose-invert-links-underline': theme(
              'colors.emerald.500 / 0.3'
            ),
            '--tw-prose-invert-bold': theme('colors.white'),
            '--tw-prose-invert-counters': theme('colors.zinc.300'),
            '--tw-prose-invert-bullets': theme('colors.zinc.300'),
            '--tw-prose-invert-hr': theme('colors.white / 0.05'),
            '--tw-prose-invert-quotes': theme('colors.zinc.100'),
            '--tw-prose-invert-quote-borders': theme('colors.zinc.700'),
            '--tw-prose-invert-captions': theme('colors.zinc.300'),
            '--tw-prose-invert-code': theme('colors.white'),
            '--tw-prose-invert-code-bg': theme('colors.zinc.700 / 0.15'),
            '--tw-prose-invert-code-ring': theme('colors.white / 0.1'),
            '--tw-prose-invert-th-borders': theme('colors.zinc.600'),
            '--tw-prose-invert-td-borders': theme('colors.zinc.700'),

            // Text elements
            p: {
              marginTop: theme('spacing.6'),
              marginBottom: theme('spacing.6'),
            },
            '[class~="lead"]': {
              fontSize: theme('fontSize.base')[0],
              ...theme('fontSize.base')[1],
            },

            // Lists - improved styling
            ol: {
              listStyleType: 'decimal',
              marginTop: theme('spacing.5'),
              marginBottom: theme('spacing.5'),
              paddingLeft: '1.625rem',
            },
            ul: {
              listStyleType: 'disc',
              marginTop: theme('spacing.5'),
              marginBottom: theme('spacing.5'),
              paddingLeft: '1.625rem',
            },
            li: {
              marginTop: theme('spacing.2'),
              marginBottom: theme('spacing.2'),
              color: 'var(--tw-prose-body)',
            },
            ':is(ol, ul) > li': {
              paddingLeft: theme('spacing[1.5]'),
            },
            'ol > li::marker': {
              fontWeight: '400',
              color: 'var(--tw-prose-counters)',
            },
            'ul > li::marker': {
              color: 'var(--tw-prose-bullets)',
            },

            hr: {
              borderColor: 'var(--tw-prose-hr)',
              marginTop: '3em',
              marginBottom: '3em',
            },
            'h1, h2, h3': {
              letterSpacing: '-0.025em',
              color: 'var(--tw-prose-headings)',
            },
            h1: {
              fontWeight: '700',
              fontSize: theme('fontSize.2xl')[0],
              ...theme('fontSize.2xl')[1],
              marginBottom: theme('spacing.2'),
            },
            h2: {
              fontWeight: '600',
              fontSize: theme('fontSize.lg')[0],
              ...theme('fontSize.lg')[1],
              marginTop: theme('spacing.16'),
              marginBottom: `${16 / 24}em`,
            },
            h3: {
              fontWeight: '600',
              fontSize: theme('fontSize.base')[0],
              ...theme('fontSize.base')[1],
              marginTop: '2.4em',
              lineHeight: '1.4',
              marginBottom: theme('spacing.2'),
            },
            h4: {
              marginTop: '2em',
              fontSize: '1.125em',
            },
            'h2 small, h3 small, h4 small': {
              fontFamily: theme('fontFamily.mono').join(', '),
              color: theme('colors.zinc.500'),
              fontWeight: 500,
            },
            'h2 small': {
              fontSize: theme('fontSize.base')[0],
              ...theme('fontSize.base')[1],
            },
            'h3 small': {
              fontSize: theme('fontSize.sm')[0],
              ...theme('fontSize.sm')[1],
            },
            'h4 small': {
              fontSize: theme('fontSize.sm')[0],
              ...theme('fontSize.sm')[1],
            },
          },
        },
        dark: {
          css: {
            color: 'var(--tw-prose-invert-body)',
            'h1, h2, h3, h4, thead th': {
              color: 'var(--tw-prose-invert-headings)',
            },
            'h2 small, h3 small, h4 small': {
              color: theme('colors.zinc.300'),
            },
            // Ensure lists have proper contrast in dark mode
            li: {
              color: 'var(--tw-prose-invert-body)',
            },
            'ol > li::marker': {
              color: 'var(--tw-prose-invert-counters)',
            },
            'ul > li::marker': {
              color: 'var(--tw-prose-invert-bullets)',
            },
          },
        },
      }),
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('@tailwindcss/forms')({
      strategy: 'class', // Only apply form styles when Tailwind classes are used
    }),
  ],
}
