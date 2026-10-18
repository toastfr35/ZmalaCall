'use strict';
// Explicit roots keep shared fixtures, manual scenarios and ad-hoc probes out of
// the requirement-based default run. Node resolves dependencies in server code.
const { readdirSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { spawnSync } = require('node:child_process');
const root = resolve(__dirname, '..');
const level = process.argv[2] || 'all';
if (!['all', 'LLT', 'HLT', 'adhoc'].includes(level)) {
  console.error('Usage: node build_tools/run-tests.cjs [all|LLT|HLT|adhoc]');
  process.exit(2);
}
const directories =
  level === 'adhoc'
    ? ['tests/adhoc/server']
    : (level === 'all' ? ['LLT', 'HLT'] : [level]).map((name) => 'tests/server/' + name);
const files = directories.flatMap((directory) =>
  readdirSync(join(root, directory))
    .filter((name) => name.endsWith('.test.js'))
    .sort()
    .map((name) => join(directory, name)),
);
if (!files.length) throw new Error('No test cases selected');
const result = spawnSync(process.execPath, ['--test', ...files], { cwd: root, stdio: 'inherit' });
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
