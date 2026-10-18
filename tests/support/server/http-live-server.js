'use strict';
// HTTP-only service for native provisioning/maintenance checks; no live accounts or SIP ports.
const fs = require('node:fs');
const { httpFixture } = require('./http-fixture');

(async () => {
  const fixture = await httpFixture();
  await fixture.store.save();
  await fixture.writeBootstrap();
  fs.writeFileSync(process.argv[2], fixture.directory);
  process.stdin.resume();
  process.stdin.on('end', async () => {
    await fixture.close();
    process.exit(0);
  });
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
