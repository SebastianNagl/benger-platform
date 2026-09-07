/** @type {import('prettier').Options} */
module.exports = {
  singleQuote: true,
  semi: false,
  plugins: ['prettier-plugin-organize-imports', 'prettier-plugin-tailwindcss'],
  // Sort imports only; never drop "unused" ones. Hoisted jest.mock factories
  // that contain JSX still need `import React` at runtime, and the organizer
  // cannot see that.
  organizeImportsSkipDestructiveCodeActions: true,
  // Tailwind v4: the plugin reads design tokens from the CSS entry point.
  tailwindStylesheet: './src/styles/tailwind.css',
}
