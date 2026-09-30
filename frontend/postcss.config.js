/**
 * PostCSS configuration for Tailwind CSS v4.
 *
 * Tailwind v4 is a PostCSS plugin built on Lightning CSS, so `autoprefixer` is no
 * longer required — vendor prefixes come from Lightning CSS itself.  It is kept
 * in devDependencies only so an older toolchain can still be used.
 */
export default {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};
