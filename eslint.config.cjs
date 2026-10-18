// Keep server/tooling globals separate from browser globals: an accidental DOM
// reference in the server (or Node API in the browser) must fail linting.
const js = require('@eslint/js');
const globals = require('globals');

module.exports = [
  {
    ignores: [
      '**/node_modules/**',
      '.venv/**',
      '**/data/**',
      'build_tools/runtime/**',
      'build_tools/tmp/**',
      'tests/adhoc/tmp/**',
      'tests/coverage/**',
      'build_tools/dist/**',
      'tmp/**',
      'requirements/output/**',
      'zmala_server/web/admin.js', // Generated from the separately linted modules.
      'zmala_server/vendor/**', // Upstream source: retain its formatting and provenance.
    ],
  },
  {
    files: ['**/*.js', '**/*.cjs'],
    rules: {
      ...js.configs.recommended.rules,
      'no-unused-vars': ['error', { args: 'none', caughtErrors: 'none', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['**/*.js', '**/*.cjs'],
    ignores: ['zmala_server/web/admin-*.js', 'requirements/product/template/*.js'],
    languageOptions: { sourceType: 'commonjs', globals: globals.node },
  },
  {
    files: ['zmala_server/web/admin-*.js', 'requirements/product/template/*.js'],
    languageOptions: { sourceType: 'module', globals: globals.browser },
  },
  {
    // Playwright evaluate callbacks execute inside the isolated browser page.
    files: ['tests/server/LLT/admin-view.test.js'],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ['zmala_server/setup-pdf.js'],
    // Provisioning rejects control bytes and explicitly tests ASCII payloads.
    rules: { 'no-control-regex': 'off' },
  },
  {
    files: ['zmala_server/callback-mailer.js'],
    // SMTP exceptions are deliberately replaced: their causes can leak secrets.
    rules: { 'preserve-caught-error': 'off' },
  },
];
