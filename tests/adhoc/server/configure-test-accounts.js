'use strict';
// Run with the server stopped; preserves the existing SIP passwords and device key.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Store, DATA } = require('../../../zmala_server/store');
const examples = require('../../../zmala_server/assets/test-portraits/accounts.json');
const portraitDir = path.join(__dirname, '../../../zmala_server/assets/test-portraits');
async function configure() {
  const old = JSON.parse(fs.readFileSync(path.join(DATA, 'server.json')));
  let running = false;
  try {
    const response = await fetch(`http://127.0.0.1:${old.http_port}/health`, {
      signal: AbortSignal.timeout(1500),
    });
    running = response.ok;
  } catch {
    // An unreachable health endpoint means there is no responding local server.
  }
  if (running) throw Error('Stop the server before updating the sample accounts.');
  const photos = {};
  fs.mkdirSync(path.join(DATA, 'photos'), { recursive: true });
  for (const id of ['term1', 'phone1']) {
    const bytes = fs.readFileSync(path.join(portraitDir, examples[id].portrait)),
      name = crypto.createHash('sha256').update(bytes).digest('hex') + '.png';
    fs.writeFileSync(path.join(DATA, 'photos', name), bytes);
    photos[id] = '/photos/' + name;
  }
  if (!fs.existsSync(path.join(DATA, 'server-before-groups.json')))
    fs.copyFileSync(path.join(DATA, 'server.json'), path.join(DATA, 'server-before-groups.json'));
  const s = new Store(),
    terminal = s.terminal('term1') ? 'term1' : 'terminal',
    phone = s.value.users.phone1 ? 'phone1' : 'test';
  if (!s.terminal(terminal) || s.value.users[phone]?.type !== 'linphone')
    throw Error('Expected the existing terminal and phone test accounts.');
  s.updateAccount(terminal, {
    id: 'term1',
    name: examples.term1.name,
    type: 'terminal',
    photo: photos.term1,
  });
  s.updateAccount(phone, {
    id: 'phone1',
    name: examples.phone1.name,
    type: 'linphone',
    photo: photos.phone1,
  });
  const p = s.requireTerminal('term1');
  s.setSettings('term1', { display_name: examples.term1.name, ...p.terminal_settings });
  for (const profile of Object.values(s.value.profiles))
    for (const c of profile.contacts || [])
      if (['term1', 'phone1'].includes(c.id)) {
        c.name = examples[c.id].name;
        c.photo = '';
      }
  if (!s.permitted('term1', 'phone1'))
    s.createGroup({
      name: Object.values(s.value.groups).some((g) => g.name === 'Family')
        ? 'Test calls'
        : 'Family',
      members: ['term1', 'phone1'],
    });
  s.changed();
  fs.writeFileSync(path.join(DATA, 'terminal.json'), JSON.stringify(s.bootstrap(), null, 2));
  console.log(
    'Configured term1 and phone1 with sample pictures and a shared calling group. Passwords and terminal identity preserved.',
  );
}
configure().catch((e) => {
  console.error(e.message);
  process.exitCode = 1;
});
