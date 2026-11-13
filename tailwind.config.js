/**
 * Tailwind CSS – konfigurácia zostavenia (npm run css).
 *
 * Farby ukazujú na CSS premenné z static/css/src/app.css (kanály RGB), takže sa prepínajú
 * so svetlou / tmavou témou a fungujú aj priehľadnosti ako text-on-surface/60.
 * Staré názvy (on-surface, surface-container, primary…) sú zachované, aby šablóny ostali čitateľné;
 * nové šablóny majú používať priame názvy (track, line, infield…). Popis systému: DESIGN.md.
 */
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js', './*.py'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        headline: ['Archivo', 'system-ui', 'sans-serif'],
        body: ['Archivo', 'system-ui', 'sans-serif'],
        data: ['Archivo', 'system-ui', 'sans-serif'],
      },
      colors: {
        // priame názvy systému „Modrá dráha“
        track: token('track'),
        'track-deep': token('track-deep'),
        ink: token('text'),
        muted: token('muted'),
        line: token('line'),
        'line-strong': token('line-strong'),
        paper: token('surface'),
        concrete: token('bg'),
        infield: token('infield'),
        warn: token('warn'),
        danger: token('danger'),
        info: token('info'),
        // staršie názvy používané v šablónach
        primary: token('track'),
        secondary: token('muted'),
        tertiary: token('info'),
        'on-surface': token('text'),
        'on-surface-variant': token('muted'),
        'surface-bright': token('surface'),
        'surface-container-lowest': token('surface'),
        'surface-container-low': token('surface'),
        'surface-container': token('surface'),
        'surface-container-high': token('surface-2'),
        'surface-container-highest': token('surface-2'),
        'primary-container': 'rgb(var(--c-track) / 0.10)',
        'secondary-container': 'rgb(var(--c-muted) / 0.12)',
        'tertiary-container': 'rgb(var(--c-info) / 0.12)',
      },
      // Zaoblené rohy systému „Modrá dráha“ (karty 16 px, tlačidlá ako pilulky – tie sú v components.css).
      borderRadius: {
        none: '0', sm: '6px', DEFAULT: '8px', md: '10px', lg: '12px',
        xl: '14px', '2xl': '18px', '3xl': '24px', full: '9999px',
      },
    },
  },
  plugins: [],
};
