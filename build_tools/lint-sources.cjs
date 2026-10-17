'use strict';

// Git supplies the source inventory so downloaded SDKs, local configuration and
// temporary experiments never become inputs. Include new, unignored source files
// before they are staged, and fail if any checker fails or cannot be launched.
const { execFileSync, spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const { resolve } = require('node:path');
const root = resolve(__dirname, '..');
const files = [
  ...new Set(
    execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], {
      cwd: root,
      encoding: 'utf8',
    }).split('\0'),
  ),
].filter((file) => file && existsSync(resolve(root, file)));

function check(command, args) {
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.error) console.error(`${command}: ${result.error.message}`);
  if (result.error || result.status !== 0) process.exitCode = 1;
}

const mode = process.argv[2];
if (mode === 'shell') {
  // MSYS2 need not be on PowerShell's PATH on the Windows development machine.
  const shell =
    process.env.LINT_SH ||
    (process.platform === 'win32' && existsSync('C:/msys64/usr/bin/sh.exe')
      ? 'C:/msys64/usr/bin/sh.exe'
      : 'sh');
  for (const file of files.filter((file) => file.endsWith('.sh'))) check(shell, ['-n', file]);
} else if (mode === 'native') {
  const options = [
    '--enable=warning,performance,portability',
    '--error-exitcode=1',
    '--inline-suppr',
    '--suppress=missingIncludeSystem',
    '--check-level=normal',
  ];
  // Older cppcheck versions classify Arduino .ino files as C. Keep C and
  // C++ inputs separate so each is checked with the correct language rules.
  for (const [language, pattern] of [
    ['c', /\.c$/],
    ['c++', /\.(cpp|ino)$/],
  ]) {
    const sources = files.filter((file) => pattern.test(file));
    if (sources.length) {
      check(process.argv[3] || 'cppcheck', [...options, `--language=${language}`, ...sources]);
    }
  }
} else {
  console.error('Usage: node build_tools/lint-sources.cjs shell|native [cppcheck]');
  process.exitCode = 1;
}
