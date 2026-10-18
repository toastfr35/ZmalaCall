// @test S-HLT-004
// @requirements HLR-SRV-DIR-001, HLR-SRV-DIR-002, HLR-SRV-AUTH-001
// @environment portable
// @plan Use the assembled admin HTTP service to create/edit/delete accounts and groups, enroll terminals and revoke access; assert derived membership and authentication boundaries persist across reload.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { httpFixture } = require('../../support/server/http-fixture');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { Store } = require('../../../zmala_server/store');

test('admin account and group CRUD, membership validation, terminal provisioning and revoked access', async () => {
  const fixture = await httpFixture();
  const { store, sipServer, base, directory: dir } = fixture;
  const admin = store.value.admin_token;
  async function request(route, method = 'GET', data, token = admin) {
    if (route === '/api/users' && method === 'POST')
      data = { emails: ['fixture@example.test'], ...data };
    const response = await fetch(base + route, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    return { status: response.status, body: await response.json() };
  }
  try {
    for (const page of ['/', '/accounts', '/groups', '/terminals', '/activity']) {
      const response = await fetch(base + page);
      assert.equal(response.status, 200);
      assert.match(await response.text(), /Main navigation/);
    }
    const redirect = await fetch(base + '/permissions', { redirect: 'manual' });
    assert.equal(redirect.status, 302);
    assert.equal(redirect.headers.get('location'), '/groups');
    assert.equal(
      (
        await request(
          '/api/users',
          'POST',
          { id: 'alice', name: 'Alice', type: 'linphone' },
          'wrong',
        )
      ).status,
      401,
    );
    assert.equal(
      (
        await request('/api/users', 'POST', {
          id: 'alice',
          name: 'Alice',
          type: 'linphone',
          password: 'test',
        })
      ).status,
      201,
    );
    assert.equal(
      (await request('/api/users', 'POST', { id: 'lounge', name: 'Lounge', type: 'terminal' }))
        .status,
      201,
    );
    const token = store.value.users.lounge.device_token;
    const config = (await request('/api/config?terminal_id=terminal', 'GET', undefined, token))
      .body;
    assert.equal(config.sip.username, 'lounge');
    assert.equal(config.call_auth_key, token);
    assert.equal((await request('/api/admin', 'GET', undefined, token)).status, 401);
    const available = '/api/contacts/alice/availability';
    assert.equal((await request(available, 'GET', undefined, 'wrong')).status, 401);
    assert.equal((await request(available, 'GET', undefined, token)).body.online, false);
    assert.equal(
      (await request('/api/status', 'POST', { state: 'home', registered: true }, token)).status,
      200,
    );
    assert.equal((await request('/api/admin')).body.terminal_statuses.lounge.state, 'home');
    const group = {
      name: 'Family test',
      description: 'Test accounts',
      members: ['alice', 'lounge'],
    };
    assert.equal((await request('/api/groups', 'POST', group, 'wrong')).status, 401);
    assert.equal(
      (
        await request('/api/groups', 'POST', {
          ...group,
          configuration_version: store.value.configuration_version - 1,
        })
      ).status,
      409,
    );
    assert.equal(store.permitted('alice', 'lounge'), false);
    const created = await request('/api/groups', 'POST', {
      ...group,
      configuration_version: store.value.configuration_version,
    });
    assert.equal(created.status, 201);
    const groupId = created.body.id;
    assert.equal(store.permitted('alice', 'lounge'), true);
    assert.equal(store.permitted('lounge', 'alice'), true);
    sipServer.registrations.set('alice', { expires: Date.now() + 60000 });
    assert.equal((await request(available, 'GET', undefined, token)).body.online, true);
    assert.equal(
      (await request('/api/config', 'GET', undefined, token)).body.contacts.find(
        (c) => c.id === 'alice',
      ).online,
      true,
    );
    sipServer.registrations.get('alice').reachable = false;
    assert.equal((await request(available, 'GET', undefined, token)).body.online, false);
    assert.equal(
      (await request('/api/config', 'GET', undefined, token)).body.contacts.find(
        (c) => c.id === 'alice',
      ).online,
      false,
    );
    sipServer.registrations.get('alice').reachable = true;
    sipServer.registrations.get('alice').expires = Date.now() - 1;
    assert.equal((await request(available, 'GET', undefined, token)).body.online, false);
    assert.equal(
      (await request('/api/config', 'GET', undefined, token)).body.contacts.find(
        (c) => c.id === 'alice',
      ).online,
      false,
    );
    sipServer.registrations.delete('alice');
    assert.equal((await request('/api/admin')).body.account_groups.alice.includes(groupId), true);
    assert.equal(
      (await request('/api/groups/' + groupId, 'PUT', { ...group, members: ['alice', 'unknown'] }))
        .status,
      400,
    );
    assert.equal(
      (await request('/api/groups/' + groupId, 'PUT', { ...group, members: ['alice', 'alice'] }))
        .status,
      400,
    );
    assert.equal((await request('/api/permissions', 'PUT', { permissions: {} })).status, 404);
    const second = await request('/api/groups', 'POST', {
      name: 'Second',
      members: ['alice', 'lounge'],
    });
    assert.equal(second.status, 201);
    assert.equal((await request('/api/groups/' + groupId, 'DELETE')).status, 200);
    assert.equal(store.permitted('alice', 'lounge'), true);
    assert.equal(
      (
        await request('/api/groups/' + second.body.id, 'PUT', {
          name: 'Second edited',
          members: ['alice'],
        })
      ).status,
      200,
    );
    assert.equal(store.permitted('alice', 'lounge'), false);
    assert.equal(
      (
        await request('/api/groups/' + second.body.id, 'PUT', {
          name: 'Second edited',
          members: ['alice', 'lounge'],
        })
      ).status,
      200,
    );
    assert.equal(
      (
        await request('/api/users/alice', 'PUT', {
          name: 'Alice',
          type: 'linphone',
          photo: '/photos/abcd.png',
        })
      ).status,
      200,
    );
    assert.equal(
      store.config('lounge').contacts.find((c) => c.id === 'alice').photo,
      '/photos/abcd.png',
    );
    assert.equal(
      (
        await request('/api/contacts', 'PUT', {
          terminal_id: 'lounge',
          contacts: [{ id: 'alice', name: 'Override', photo: '/photos/ffff.png' }],
        })
      ).status,
      404,
    );
    assert.equal(
      (await request('/api/config', 'GET', undefined, token)).body.contacts.find(
        (c) => c.id === 'alice',
      ).name,
      'Alice',
    );
    assert.equal(
      store.config('lounge').contacts.find((c) => c.id === 'alice').photo,
      '/photos/abcd.png',
    );
    assert.equal(
      (
        await request('/api/settings', 'PUT', {
          terminal_id: 'lounge',
          display_name: 'Living room',
          auto_answer_seconds: 9,
          camera: '',
          microphone: '',
          speaker: '',
        })
      ).status,
      200,
    );
    assert.equal(store.config('lounge').display_name, 'Living room');
    assert.notEqual(store.config('term1').display_name, 'Living room');
    assert.equal(store.config('lounge').language, 'en');
    assert.equal(store.config('lounge').command_shell, 'powershell');
    assert.equal(store.config('lounge').auto_answer_seconds, 9);
    const answerSettings = {
      terminal_id: 'lounge',
      display_name: 'Living room',
      camera: '',
      microphone: '',
      speaker: '',
      auto_answer: true,
      auto_answer_seconds: 12,
    };
    assert.equal((await request('/api/settings', 'PUT', answerSettings)).status, 200);
    assert.equal(store.config('lounge').auto_answer, true);
    assert.equal(store.config('lounge').auto_answer_seconds, 12);
    const answerSnapshot = JSON.stringify(store.value);
    for (const invalid of [
      { auto_answer: 'yes' },
      { auto_answer_seconds: 4 },
      { auto_answer_seconds: 601 },
    ]) {
      assert.equal(
        (await request('/api/settings', 'PUT', { ...answerSettings, ...invalid })).status,
        400,
      );
      assert.equal(JSON.stringify(store.value), answerSnapshot);
    }
    // Editing account details no longer supplies or clears terminal answer settings.
    assert.equal(
      (await request('/api/users/lounge', 'PUT', { name: 'Lounge', type: 'terminal' })).status,
      200,
    );
    assert.equal(store.config('lounge').auto_answer, true);
    assert.equal(store.config('lounge').auto_answer_seconds, 12);

    const languageSettings = {
      terminal_id: 'lounge',
      display_name: 'Living room',
      language: 'fr',
      camera: '',
      microphone: '',
      speaker: '',
    };
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal((await request('/api/config', 'GET', undefined, token)).body.language, 'fr');
    assert.equal(store.config('term1').language, 'en');
    assert.equal(new Store(dir).config('lounge').language, 'fr');
    assert.equal(store.config('lounge').audio_profile, 'normal');
    assert.equal(
      (await request('/api/settings', 'PUT', { ...languageSettings, audio_profile: 'speech' }))
        .status,
      200,
    );
    assert.equal(
      (await request('/api/config', 'GET', undefined, token)).body.audio_profile,
      'speech',
    );
    assert.equal(new Store(dir).config('lounge').audio_profile, 'speech');
    assert.equal(store.config('term1').audio_profile, 'normal');
    const beforeAudio = JSON.stringify(store.value);
    for (const audio_profile of ['invalid', 'constructor', null, 16000])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, audio_profile })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), beforeAudio);
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').audio_profile, 'speech');
    assert.equal(store.config('lounge').carousel_portraits, 3);
    for (const carousel_portraits of [3, 5]) {
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, carousel_portraits })).status,
        200,
      );
      assert.equal(
        (await request('/api/config', 'GET', undefined, token)).body.carousel_portraits,
        carousel_portraits,
      );
      assert.equal(new Store(dir).config('lounge').carousel_portraits, carousel_portraits);
      assert.equal(store.config('term1').carousel_portraits, 3);
    }
    const beforeCarousel = JSON.stringify(store.value);
    for (const carousel_portraits of [0, 4, 6, 3.5, '5', true, null, {}])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, carousel_portraits })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), beforeCarousel);
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').carousel_portraits, 5);
    assert.equal(store.config('lounge').video_resolution, '720p');
    for (const video_resolution of ['480p', '720p', '1080p']) {
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, video_resolution })).status,
        200,
      );
      assert.equal(
        (await request('/api/config', 'GET', undefined, token)).body.video_resolution,
        video_resolution,
      );
      assert.equal(new Store(dir).config('lounge').video_resolution, video_resolution);
      assert.equal(store.config('term1').video_resolution, '720p');
    }
    const beforeVideo = JSON.stringify(store.value);
    for (const video_resolution of ['vga', '4k', null, 1080, {}])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, video_resolution })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), beforeVideo);
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').video_resolution, '1080p');
    assert.equal(store.config('lounge').video_fps, 15);
    for (const video_fps of [10, 15, 20, 25, 30]) {
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, video_fps })).status,
        200,
      );
      assert.equal(
        (await request('/api/config', 'GET', undefined, token)).body.video_fps,
        video_fps,
      );
      assert.equal(new Store(dir).config('lounge').video_fps, video_fps);
      assert.equal(store.config('term1').video_fps, 15);
    }
    const beforeFps = JSON.stringify(store.value);
    for (const video_fps of [0, 14, 60, 29.97, '30', true, null, {}])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, video_fps })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), beforeFps);
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').video_fps, 30, 'Unrelated saves preserve the frame rate');
    assert.equal(store.config('lounge').c20_speaker_volume, 50);
    for (const c20_speaker_volume of [0, 75, 100]) {
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, c20_speaker_volume })).status,
        200,
      );
      assert.equal(
        (await request('/api/config', 'GET', undefined, token)).body.c20_speaker_volume,
        c20_speaker_volume,
      );
      assert.equal(new Store(dir).config('lounge').c20_speaker_volume, c20_speaker_volume);
      assert.equal(store.config('term1').c20_speaker_volume, 50);
    }
    const beforeVolume = JSON.stringify(store.value);
    for (const c20_speaker_volume of [-1, 101, 50.5, '50', true, null, {}])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, c20_speaker_volume })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), beforeVolume);
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').c20_speaker_volume, 100);
    assert.equal(
      (await request('/api/settings', 'PUT', { ...languageSettings, command_shell: 'cmd' })).status,
      200,
    );
    assert.equal((await request('/api/config', 'GET', undefined, token)).body.command_shell, 'cmd');
    assert.equal(new Store(dir).config('lounge').command_shell, 'cmd');
    assert.equal(store.config('term1').command_shell, 'powershell');
    assert.equal((await request('/api/settings', 'PUT', languageSettings)).status, 200);
    assert.equal(store.config('lounge').command_shell, 'cmd');
    for (const command_shell of ['zsh', 'constructor', null, 5])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, command_shell })).status,
        400,
      );
    const unchanged = JSON.stringify(store.value);
    for (const language of ['invalid', 'constructor', null, 5])
      assert.equal(
        (await request('/api/settings', 'PUT', { ...languageSettings, language })).status,
        400,
      );
    assert.equal(JSON.stringify(store.value), unchanged);
    const languages = (await request('/api/admin')).body.terminal_languages;
    for (const code of ['en', 'fr', 'es', 'pt', 'zh-Hans', 'ja', 'ko', 'ar', 'hi', 'th'])
      assert.equal(
        languages.some((l) => l.code === code),
        true,
      );
    assert.equal((await request('/api/local-terminal', 'PUT', { id: 'lounge' })).status, 200);
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir, 'terminal.json'))).device_token, token);
    assert.equal((await request('/api/terminal-bootstrap?id=lounge')).body.device_token, token);
    assert.equal((await request('/api/local-terminal', 'PUT', { id: 'alice' })).status, 400);
    sipServer.dialogs.set('call', { peers: [{ user: 'lounge' }, { user: 'alice' }] });
    assert.equal(
      (await request('/api/users/lounge', 'PUT', { id: 'room', name: 'Lounge', type: 'terminal' }))
        .status,
      409,
    );
    assert.equal(
      (
        await request('/api/users/lounge', 'PUT', {
          name: 'Lounge',
          type: 'terminal',
          auto_answer: true,
          auto_answer_seconds: 8,
        })
      ).status,
      200,
    );
    assert.equal((await request('/api/config', 'GET', undefined, token)).body.auto_answer, true);
    assert.equal((await request('/api/users/lounge', 'DELETE')).status, 409);
    assert.equal(store.terminal('lounge'), true);
    assert.equal(
      (await request('/api/users/lounge', 'PUT', { name: 'New name', type: 'linphone' })).status,
      409,
    );
    sipServer.dialogs.clear();
    sipServer.registrations.set('lounge', {});
    assert.equal(
      (await request('/api/users/lounge', 'PUT', { id: 'room', name: 'Room', type: 'terminal' }))
        .body.id,
      'room',
    );
    assert.equal(sipServer.registrations.has('lounge'), false);
    assert.equal(store.value.local_terminal_id, 'room');
    assert.equal((await request('/api/config', 'GET', undefined, token)).body.sip.username, 'room');
    assert.equal(store.value.groups[second.body.id].members.includes('room'), true);
    assert.equal(store.value.groups[second.body.id].members.includes('lounge'), false);
    assert.equal((await request('/api/terminal-bootstrap?id=room')).body.device_token, token);
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir, 'terminal.json'))).device_token, token);
    assert.equal(
      (await request('/api/users/room', 'PUT', { id: 'lounge', name: 'Lounge', type: 'terminal' }))
        .status,
      200,
    );
    sipServer.registrations.set('lounge', {});
    assert.equal((await request('/api/users/lounge', 'DELETE')).status, 200);
    assert.equal(sipServer.registrations.has('lounge'), false);
    assert.equal(store.value.local_terminal_id, 'term1');
    assert.deepEqual(store.value.groups[second.body.id].members, ['alice']);
    assert.equal((await request('/api/config', 'GET', undefined, token)).status, 401);
    assert.equal(
      (
        await request('/api/users/alice', 'PUT', {
          name: 'Alice terminal',
          type: 'terminal',
          password: 'replacement',
        })
      ).status,
      200,
    );
    assert.equal(store.config('alice').sip.password, 'replacement');
    assert.equal((await request('/api/users/alice', 'DELETE')).status, 200);
    assert.equal((await request('/api/users/term1', 'DELETE')).status, 200);
    assert.equal(store.value.local_terminal_id, null);
    assert.equal(store.bootstrap().device_id, 'unassigned');
    assert.equal(
      (await request('/api/users/newterminal', 'PUT', { name: 'Missing', type: 'terminal' }))
        .status,
      400,
    );
    assert.equal(
      (
        await request('/api/users', 'POST', {
          id: 'replacement',
          name: 'Replacement',
          type: 'terminal',
        })
      ).status,
      201,
    );
    assert.equal(store.value.local_terminal_id, 'replacement');
  } finally {
    await fixture.close();
  }
});
