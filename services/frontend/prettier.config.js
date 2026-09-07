/** @type {import('prettier').Options} */
module.exports = {
  singleQuote: true,
  semi: false,
  plugins: ['prettier-plugin-organize-imports', 'prettier-plugin-tailwindcss'],
  // Tailwind v4: the plugin reads design tokens from the CSS entry point.
  tailwindStylesheet: './src/styles/tailwind.css',
}
