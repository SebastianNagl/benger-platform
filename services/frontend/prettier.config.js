/** @type {import('prettier').Options} */
module.exports = {
  singleQuote: true,
  semi: false,
  plugins: ['prettier-plugin-organize-imports', 'prettier-plugin-tailwindcss'],
  // Sort imports only; never drop "unused" ones. Hoisted jest.mock factories
  // that contain JSX still need `import React` at runtime, and the organizer
  // cannot see that.
  organizeImportsSkipDestructiveCodeActions: true,
  // Keep whitespace inside class strings: without this the Tailwind plugin
  // trims the leading space of a conditional segment in template literals
  // (`p-6${x ? ' shadow' : ''}` -> `p-6${x ? 'shadow' : ''}` = "p-6shadow"),
  // which cost the landing news cards their padding on 2026-09-08.
  tailwindPreserveWhitespace: true,
  // Tailwind v4: the plugin reads design tokens from the CSS entry point.
  tailwindStylesheet: './src/styles/tailwind.css',
}
