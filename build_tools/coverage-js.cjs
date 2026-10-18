'use strict';
// Instrument authored JavaScript only. Unloaded files are seeded with zero hits.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { createInstrumenter } = require('istanbul-lib-instrument');
const { createCoverageMap } = require('istanbul-lib-coverage');
const root = path.resolve(__dirname, '..');
const output = process.env.ZMALA_COVERAGE_DIR;
const instrumenter = createInstrumenter({ compact: false, produceSourceMap: false });
const cache = new Map();
const originalRead = fs.readFileSync.bind(fs);

function eligible(file) {
  const name = path.relative(root, file).replaceAll('\\', '/');
  return (
    name.startsWith('zmala_server/') &&
    name.endsWith('.js') &&
    !name.includes('/vendor/') &&
    !name.includes('/node_modules/') &&
    !name.includes('/data/') &&
    name !== 'zmala_server/web/admin.js'
  );
}

function source(file) {
  file = path.resolve(file);
  if (!output || !eligible(file)) return originalRead(file, 'utf8');
  if (!cache.has(file))
    cache.set(file, instrumenter.instrumentSync(originalRead(file, 'utf8'), file));
  return cache.get(file);
}

function runInNewContext(code, context) {
  if (output) context.__coverage__ = globalThis.__coverage__ ||= {};
  return require('node:vm').runInNewContext(code, context);
}

function browserSource(file) {
  if (!output || path.basename(file) !== 'admin.js') return originalRead(file);
  // Keep exactly the production bundle's module ordering; never write an
  // instrumented asset into the application or count its generated wrapper.
  const bundle = originalRead(file, 'utf8');
  const modules = [...bundle.matchAll(/^\/\/ (admin-[a-z]+\.js)$/gm)].map((match) =>
    source(path.join(path.dirname(file), match[1]))
      .replace(/^import[^;]+;\s*/gm, '')
      .replace(/^export /gm, ''),
  );
  if (!modules.length) throw Error('Cannot find admin bundle source modules');
  return '(() => {\n' + modules.join('\n') + '\n})();';
}

async function collectPage(page) {
  if (!output) return;
  const data = await page.evaluate('globalThis.__coverage__ || {}');
  const map = createCoverageMap(globalThis.__coverage__ || {});
  map.merge(data);
  globalThis.__coverage__ = map.toJSON();
}

function install() {
  if (!output) throw Error('ZMALA_COVERAGE_DIR is required');
  fs.mkdirSync(output, { recursive: true });
  const previous = Module._extensions['.js'];
  Module._extensions['.js'] = (module, file) => {
    if (eligible(file)) module._compile(source(file), file);
    else previous(module, file);
  };
  process.on('exit', () =>
    fs.writeFileSync(
      path.join(output, `node-${process.pid}.json`),
      JSON.stringify(globalThis.__coverage__ || {}),
    ),
  );
}

function report() {
  const { createContext } = require('istanbul-lib-report');
  const reports = require('istanbul-reports');
  const map = createCoverageMap({});
  function walk(folder) {
    for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
      if (['vendor', 'node_modules', 'data'].includes(entry.name)) continue;
      const file = path.join(folder, entry.name);
      if (entry.isDirectory()) walk(file);
      else if (eligible(file)) {
        instrumenter.instrumentSync(originalRead(file, 'utf8'), file);
        map.addFileCoverage(instrumenter.lastFileCoverage());
      }
    }
  }
  walk(path.join(root, 'zmala_server'));
  for (const name of fs.readdirSync(output).filter((name) => /^node-\d+\.json$/.test(name)))
    map.merge(JSON.parse(originalRead(path.join(output, name), 'utf8')));
  const context = createContext({ dir: path.dirname(output), coverageMap: map });
  for (const format of ['html', 'json', 'json-summary', 'lcovonly'])
    reports.create(format).execute(context);
}

if (require.main === module) report();
else if (process.env.ZMALA_COVERAGE_PRELOAD === '1') install();
module.exports = { source, runInNewContext, browserSource, collectPage };
