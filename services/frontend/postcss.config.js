/** @type {import('postcss-load-config').Config} */
// Tailwind CSS v4: the PostCSS plugin moved to @tailwindcss/postcss and
// handles imports and vendor prefixing itself (no autoprefixer needed).
const config = {
  plugins: {
    '@tailwindcss/postcss': {},
  },
}

module.exports = config
