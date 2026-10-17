'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const dgram = require('node:dgram');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sip = require('sip');
const digest = require('sip/digest');
const { DigestAuth } = require('../auth');
const { Store } = require('../store');
const { MediaRelay } = require('../media');
const { SipServer } = require('../sip-server');
const proxy = require('sip/proxy');
const crypto = require('node:crypto');

test('digest rejects replay, wrong password, and a changed target', () => {
  const auth = new DigestAuth('family.test'),
    users = { alice: { password: 'correct' } };
  function signed(password = 'correct') {
    const rq = { method: 'REGISTER', uri: 'sip:family.test', headers: {} };
    const rs = auth.challenge(rq);
    digest.signRequest({}, rq, rs, { user: 'alice', password });
    return rq;
  }
  const rq = signed();
  assert.equal(auth.verify(rq, users), 'alice');
  assert.equal(auth.verify(rq, users), null);
  assert.equal(auth.verify(signed('wrong'), users), null);
  const malformed = signed();
  malformed.headers.authorization[0].response = 'é'.repeat(32);
  assert.equal(auth.verify(malformed, users), null, 'Non-hex digests must fail without throwing');
  const altered = signed();
  altered.uri = 'sip:elsewhere';
  assert.equal(auth.verify(altered, users), null);
});
test('group membership persists, denies unknown/self calls, and derives terminal contacts', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-call-'));
  try {
    const s = new Store(dir);
    assert.equal(s.permitted('phone1', 'term1'), true);
    assert.equal(s.permitted('term1', 'phone1'), true);
    assert.equal(s.permitted('unknown', 'term1'), false);
    assert.equal(s.permitted('phone1', 'phone1'), false);
    assert.equal(s.permitted('constructor', 'term1'), false);
    s.deleteGroup('family');
    const second = new Store(dir);
    assert.equal(second.permitted('phone1', 'term1'), false);
    assert.equal(second.value.users.phone1.password, s.value.users.phone1.password);
    assert.equal(second.config().contacts[0].can_call, false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('legacy migrations retain credentials and metadata, and convert only mutual edges without transitive access', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-migration-'));
  try {
    const legacy = {
      schema_version: 1,
      configuration_version: 7,
      host: '192.168.1.8',
      sip_port: 5060,
      http_port: 8080,
      admin_token: 'admin',
      device_id: 'existing-device',
      device_token: 'existing-token',
      display_name: 'Grandma',
      auto_answer_seconds: 8,
      terminal_settings: { camera: 'camera', microphone: '', speaker: '' },
      users: {
        terminal: { name: 'Terminal', password: 'terminal-secret' },
        test: { name: 'Alice', password: 'test' },
      },
      contacts: [
        {
          id: 'test',
          name: 'Alice',
          can_call: true,
          can_receive: true,
          auto_answer: true,
          photo: '/photos/abcd.png',
        },
      ],
    };
    fs.writeFileSync(path.join(dir, 'server.json'), JSON.stringify(legacy));
    const s = new Store(dir);
    assert.equal(s.value.schema_version, 6);
    assert.equal(s.value.users.test.password, 'test');
    assert.equal(s.config().sip.password, 'terminal-secret');
    assert.equal(s.config().device_id, 'existing-device');
    assert.equal(s.config().call_auth_key, 'existing-token');
    assert.equal(s.config().contacts[0].photo, '');
    assert.equal(s.config().auto_answer, true);
    assert.equal(s.config().auto_answer_seconds, 8);
    assert.equal(s.permitted('test', 'terminal'), true);
    assert.equal(s.value.configuration_version, 10);
    assert.equal(new Store(dir).value.configuration_version, 10);
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'linphone' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'carol',
      name: 'Carol',
      type: 'linphone',
    });
    const v = s.value;
    v.schema_version = 3;
    v.permissions = Object.fromEntries(
      Object.keys(v.users).map((id) => [
        id,
        Object.fromEntries(Object.keys(v.users).map((other) => [other, false])),
      ]),
    );
    v.permissions.test.terminal = v.permissions.terminal.test = true;
    v.permissions.test.bob = v.permissions.bob.test = true;
    v.permissions.bob.carol = true;
    delete v.groups;
    s.save();
    const migrated = new Store(dir);
    assert.equal(migrated.permitted('test', 'bob'), true);
    assert.equal(migrated.permitted('terminal', 'bob'), false);
    assert.equal(migrated.permitted('bob', 'carol'), false);
    assert.equal('permissions' in migrated.value, false);
    assert.equal(migrated.accountGroups('test').length, 2);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('overlapping groups allow direct shared membership, all types, removal, rename and optional account pictures', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-groups-'));
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'Alice',
      type: 'linphone',
      photo: '/photos/abcd.png',
    });
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'linphone' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'lounge',
      name: 'Lounge',
      type: 'terminal',
      auto_answer: true,
      auto_answer_seconds: 7,
    });
    assert.equal(s.permitted('alice', 'lounge'), false);
    const a = s.createGroup({ name: 'Family A', members: ['alice', 'lounge'] }),
      b = s.createGroup({ name: 'Family B', members: ['alice', 'bob'] });
    assert.equal(s.accountGroups('alice').length, 2);
    assert.equal(s.permitted('alice', 'bob'), true);
    assert.equal(s.permitted('bob', 'alice'), true);
    assert.equal(s.permitted('bob', 'lounge'), false);
    assert.equal(s.config('lounge').contacts.find((c) => c.id === 'alice').auto_answer, true);
    assert.equal(
      s.config('lounge').contacts.find((c) => c.id === 'alice').photo,
      '/photos/abcd.png',
    );
    const another = s.createGroup({ name: 'Another', members: ['alice', 'lounge'] });
    s.deleteGroup(a);
    assert.equal(s.permitted('alice', 'lounge'), true);
    s.updateGroup(another, { name: 'Another edited', members: ['lounge'] });
    assert.equal(s.permitted('alice', 'lounge'), false);
    assert.equal(s.value.users.lounge.auto_answer, true);
    s.updateGroup(another, { name: 'Another edited', members: ['alice', 'lounge'] });
    s.selectTerminal('lounge');
    const identity = s.value.users.lounge.device_id,
      token = s.value.users.lounge.device_token,
      password = s.value.users.lounge.password;
    const before = JSON.stringify(s.value);
    assert.throws(() => s.updateAccount('lounge', { id: 'alice', name: 'Bad', type: 'linphone' }));
    assert.equal(JSON.stringify(s.value), before);
    s.updateAccount('lounge', { id: 'livingroom', name: 'Living room', type: 'terminal' });
    assert.equal(s.deviceAccount(token), 'livingroom');
    assert.equal(s.config().sip.username, 'livingroom');
    assert.equal(s.value.users.livingroom.device_id, identity);
    assert.equal(s.value.users.livingroom.password, password);
    assert.equal(s.permitted('alice', 'livingroom'), true);
    assert.equal(s.permitted('alice', 'lounge'), false);
    assert.equal(s.contacts('term1').find((c) => c.id === 'livingroom').name, 'Living room');
    assert.equal(s.contacts('term1').find((c) => c.id === 'livingroom').photo, '');
    s.deleteAccount('alice');
    assert.deepEqual(s.value.groups[b].members, ['bob']);
    assert.equal(s.permitted('alice', 'livingroom'), false);
    assert.equal(
      s.config().contacts.some((c) => c.id === 'alice'),
      false,
    );
    assert.equal(new Store(dir).config().sip.username, 'livingroom');
    s.updateAccount('bob', { name: 'Bob terminal', type: 'terminal' });
    const bobToken = s.value.users.bob.device_token;
    s.updateAccount('bob', { name: 'Bob phone', type: 'linphone' });
    assert.equal(s.deviceAccount(bobToken), undefined);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('invalid groups and account settings do not partially change permissions or credentials', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-validation-'));
  try {
    const s = new Store(dir),
      before = JSON.stringify(s.value);
    for (const g of [
      { name: '', members: [] },
      { name: 'Family', members: [] },
      { name: 'Bad', members: ['unknown'] },
      { name: 'Bad', members: ['phone1', 'phone1'] },
      { name: 'Bad', members: 'phone1' },
      { name: 'Bad', members: ['constructor'] },
      { name: 'Bad', members: [], description: 5 },
    ])
      assert.throws(() => s.createGroup(g));
    assert.throws(() => s.updateGroup('family', { name: 'Bad', members: ['unknown'] }));
    assert.throws(() => s.deleteGroup('constructor'));
    assert.throws(() =>
      s.updateAccount('phone1', { name: 'phone1', type: 'linphone', auto_answer: true }),
    );
    assert.throws(() =>
      s.updateAccount('term1', { name: 'term1', type: 'terminal', auto_answer_seconds: 2 }),
    );
    assert.throws(() =>
      s.updateAccount('phone1', {
        name: 'phone1',
        type: 'linphone',
        photo: 'https://example.com/photo.png',
      }),
    );
    assert.equal(JSON.stringify(s.value), before);
    const empty = s.createGroup({ name: 'Empty', members: [] });
    assert.deepEqual(s.value.groups[empty].members, []);
    s.updateAccount('phone1', { name: 'phone1', type: 'linphone', photo: '/photos/abcd.png' });
    assert.equal(s.config().contacts[0].photo, '/photos/abcd.png');
    s.updateAccount('phone1', { name: 'phone1', type: 'linphone', photo: '/photos/ffff.png' });
    assert.equal(s.config().contacts[0].photo, '/photos/ffff.png');
    s.updateAccount('phone1', { name: 'phone1', type: 'linphone', photo: '' });
    assert.equal(s.config().contacts[0].photo, '');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('SIP routing enforces groups and authenticates every terminal recipient', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-routing-')),
    send = proxy.send,
    encodeFlowUri = sip.encodeFlowUri;
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'Alice',
      type: 'linphone',
    });
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'linphone' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'lounge',
      name: 'Lounge',
      type: 'terminal',
    });
    const server = new SipServer(s),
      sent = [];
    proxy.send = (message) => sent.push(message);
    sip.encodeFlowUri = (flow) => `sip:${flow.address}:${flow.port}`;
    server.auth.verify = () => 'alice';
    const peer = { address: '127.0.0.1', port: 50001, protocol: 'UDP' },
      target = { address: '127.0.0.1', port: 50002, protocol: 'UDP' };
    for (const id of ['bob', 'lounge'])
      server.registrations.set(id, {
        contact: { uri: `sip:${id}@127.0.0.1:50002` },
        remote: target,
        expires: Date.now() + 60000,
      });
    const request = (to) => ({
      method: 'INVITE',
      uri: `sip:${to}@${s.value.host}`,
      headers: {
        to: { uri: `sip:${to}@${s.value.host}`, params: {} },
        from: { uri: `sip:alice@${s.value.host}`, params: { tag: 'alice-tag' } },
        via: [],
        cseq: { seq: 1, method: 'INVITE' },
        'call-id': 'test-' + to,
        contact: [{ uri: 'sip:alice@127.0.0.1:50001' }],
        'x-family-auth': 'forged',
      },
      content: '',
    });
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
    const group = s.createGroup({ name: 'Peers', members: ['alice', 'bob', 'lounge'] });
    await server.request(request('bob'), peer);
    const phone = sent.pop();
    assert.equal(phone.method, 'INVITE');
    assert.equal(phone.headers['x-family-auth'], undefined);
    await server.request(request('lounge'), peer);
    assert.equal(sent.pop().status, 486);
    server.dialogs.clear();
    await server.request(request('lounge'), peer);
    const terminal = sent.pop();
    const proof = crypto
      .createHmac('sha256', s.value.users.lounge.device_token)
      .update('test-lounge:alice')
      .digest('hex');
    assert.equal(terminal.headers['x-family-auth'], proof);
    assert.notEqual(
      proof,
      crypto
        .createHmac('sha256', s.value.users.term1.device_token)
        .update('test-lounge:alice')
        .digest('hex'),
    );
    server.dialogs.clear();
    s.deleteGroup(group);
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
  } finally {
    proxy.send = send;
    if (encodeFlowUri) sip.encodeFlowUri = encodeFlowUri;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('audio/video SDP uses relay ports and actual signalling peers, with bidirectional RTP and RTCP', async () => {
  const relay = new MediaRelay('127.0.0.1', 24000, 24050),
    peers = [];
  async function peer() {
    const s = dgram.createSocket('udp4');
    await new Promise((r) => s.bind(0, '127.0.0.1', r));
    peers.push(s);
    return s;
  }
  try {
    const a = await peer(),
      b = await peer();
    const sdp = (port) =>
      `v=0\r\no=- 1 1 IN IP4 8.8.8.8\r\ns=-\r\nc=IN IP4 8.8.8.8\r\nt=0 0\r\nm=audio ${port} RTP/AVP 0\r\na=rtcp-mux\r\na=ice-ufrag:test\r\na=candidate:bad\r\nm=video ${port} RTP/AVP 96\r\na=rtpmap:96 VP8/90000\r\n`;
    const offer = await relay.rewrite('test', sdp(a.address().port), 0, '127.0.0.1');
    const answer = await relay.rewrite('test', sdp(b.address().port), 1, '127.0.0.1');
    assert.match(offer, /c=IN IP4 127.0.0.1/);
    assert.doesNotMatch(offer, /rtcp-mux|ice-ufrag|candidate/);
    const leg = relay.sessions.get('test').streams[0];
    assert.match(offer, new RegExp(`m=audio ${leg[1].rtp.port} `));
    assert.match(answer, new RegExp(`m=audio ${leg[0].rtp.port} `));
    for (const kind of ['rtp', 'rtcp']) {
      leg[0][kind + 'Target'] = { address: '127.0.0.1', port: a.address().port };
      leg[1][kind + 'Target'] = { address: '127.0.0.1', port: b.address().port };
      for (const [sender, receiver, side] of [
        [a, b, 0],
        [b, a, 1],
      ]) {
        const packet = Buffer.from([128, 96, 1, 2, 3, 4, 5, 6]);
        const received = new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(Error('relay timeout')), 2000);
          receiver.once('message', (bytes) => {
            clearTimeout(timer);
            resolve(bytes);
          });
        });
        sender.send(packet, leg[side][kind].port, '127.0.0.1');
        assert.deepEqual(await received, packet);
      }
    }
    relay.close('test');
    assert.equal(relay.used.size, 0);
    await assert.rejects(
      relay.rewrite('bundle', sdp(2000) + 'a=group:BUNDLE 0 1\r\n', 0, '127.0.0.1'),
    );
  } finally {
    relay.closeAll();
    for (const s of peers) s.close();
  }
});

test('contacts always follow account names and pictures, sort alphabetically, and ignore legacy overrides', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-contacts-'));
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'zoe',
      name: 'Zoë',
      type: 'linphone',
      photo: '/photos/abcd.png',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'alice',
      type: 'linphone',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'emile',
      name: 'Émile',
      type: 'linphone',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alicia',
      name: 'Alice',
      type: 'linphone',
    });
    s.createGroup({ name: 'Contacts', members: ['term1', 'zoe', 'alice', 'emile', 'alicia'] });
    s.value.profiles.term1.contacts = [
      { id: 'zoe', name: 'A custom name', photo: '/photos/ffff.png' },
      { id: 'alice', name: 'Z custom name', photo: '/photos/aaaa.png' },
    ];
    s.save();
    const config = new Store(dir).config('term1');
    assert.deepEqual(
      config.contacts.filter((c) => c.can_call).map((c) => c.id),
      ['alice', 'alicia', 'emile', 'phone1', 'zoe'],
    );
    const zoe = config.contacts.find((c) => c.id === 'zoe');
    assert.equal(zoe.name, 'Zoë');
    assert.equal(zoe.photo, '/photos/abcd.png');
    assert.equal('photo_override' in zoe, false);
    assert.equal(config.contacts.find((c) => c.id === 'alice').photo, '');
    s.updateAccount('zoe', { name: 'Aaron', type: 'linphone', photo: '/photos/bbbb.png' });
    assert.equal(s.config().contacts[0].name, 'Aaron');
    assert.equal(s.config().contacts[0].photo, '/photos/bbbb.png');
    s.updateAccount('zoe', { name: 'Aaron', type: 'linphone', photo: '' });
    assert.equal(s.config().contacts[0].photo, '');
    s.deleteAccount('emile');
    assert.equal(
      s.contacts('term1').some((c) => c.id === 'emile'),
      false,
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
