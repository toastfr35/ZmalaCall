# Product requirements

Generated from [Doorstop ZMC records](requirements/product/). Edit the YAML records, then run `build_tools/publish-requirements.ps1`.

- [1.0 Independent platform components _(ZMC001)_](#ZMC001)
- [2.0 Accounts and shared groups _(ZMC002)_](#ZMC002)
- [3.0 Accessible physical controls _(ZMC003)_](#ZMC003)
- [4.0 Audio and video calls _(ZMC004)_](#ZMC004)
- [5.0 Reset and QR setup _(ZMC005)_](#ZMC005)
- [6.0 Terminal languages _(ZMC006)_](#ZMC006)
- [7.0 Callback requests _(ZMC007)_](#ZMC007)
- [8.0 Remote maintenance _(ZMC008)_](#ZMC008)
- [9.0 Administration and persistent state _(ZMC009)_](#ZMC009)
- [10 Contact notifications and caller cancellation _(ZMC010)_](#ZMC010)

<a id="ZMC001"></a>

## 1.0 Independent platform components _(ZMC001)_

The system shall provide independently startable and stoppable server and terminal components. The server shall run on Raspberry Pi OS/Linux. Windows shall provide terminal desktop launchers and SSH-based Pi installers; Linux shall provide the documented server and terminal services and native media adapters. The platform and hardware acceptance matrix shall distinguish source-level support from verified hardware deployment.

> `README.md`

*Child links:* [SERV001 Independent server and LAN administration](server_requirements.md#SERV001), [TERM001 Independent terminal launch](terminal_requirements.md#TERM001), [SERV018 Pi server installation and service controls](server_requirements.md#SERV018)

<a id="ZMC002"></a>

## 2.0 Accounts and shared groups _(ZMC002)_

The system shall use one SIP server/domain for multiple phone and terminal accounts and permit calls only between accounts sharing a group.

> `zmala_server/tests/server.test.js`

*Child links:* [SERV002 Account management](server_requirements.md#SERV002), [SERV003 Group permissions](server_requirements.md#SERV003), [SERV004 Derived terminal contacts](server_requirements.md#SERV004)

<a id="ZMC003"></a>

## 3.0 Accessible physical controls _(ZMC003)_

The terminal shall let an elderly user choose a familiar person and control calls using LEFT, RIGHT, GREEN and RED, without clickable screen controls.

> `zmala_terminal/common/tests/test_terminal.py`

*Child links:* [TERM002 Contact identity and carousel](terminal_requirements.md#TERM002), [TERM003 Contact availability](terminal_requirements.md#TERM003), [TERM004 Call confirmation](terminal_requirements.md#TERM004), [TERM005 Physical-button prompts](terminal_requirements.md#TERM005), [SERV007 Online presence](server_requirements.md#SERV007), [TERM010 Connectivity indicator](terminal_requirements.md#TERM010), [TERM022 Interrupted or changed confirmation](terminal_requirements.md#TERM022), [TERM025 Presenter motion volume control](terminal_requirements.md#TERM025), [TERM026 Local settings with remote control](terminal_requirements.md#TERM026), [TERM028 TV setup and idle restoration](terminal_requirements.md#TERM028)

<a id="ZMC004"></a>

## 4.0 Audio and video calls _(ZMC004)_

The system shall support bidirectional audio/video calls between permitted phone and terminal accounts.

> `zmala_terminal/common/tests/accounts_live.py`

*Child links:* [SERV005 Authenticated SIP and media routing](server_requirements.md#SERV005), [TERM007 Incoming calls and auto-answer](terminal_requirements.md#TERM007), [TERM008 Active call controls](terminal_requirements.md#TERM008), [TERM009 Missing remote video](terminal_requirements.md#TERM009)

<a id="ZMC005"></a>

## 5.0 Reset and QR setup _(ZMC005)_

The terminal shall support a deliberate factory reset followed by camera-based Wi-Fi and server QR configuration; administration shall provide printable setup PDFs.

> `zmala_terminal/common/tests/provisioning_ui.py`

*Child links:* [SERV013 Printable QR downloads](server_requirements.md#SERV013), [TERM017 Factory reset access](terminal_requirements.md#TERM017), [TERM018 Factory reset scope](terminal_requirements.md#TERM018), [TERM019 QR enrollment sequence](terminal_requirements.md#TERM019), [TERM020 Stable camera QR scanning](terminal_requirements.md#TERM020), [TERM027 Remote onboarding and status](terminal_requirements.md#TERM027)

<a id="ZMC006"></a>

## 6.0 Terminal languages _(ZMC006)_

The terminal shall support the provided European and Asian languages while administration remains in English.

> `zmala_terminal/common/tests/terminal_languages_ui.py`

*Child links:* [SERV012 Terminal settings](server_requirements.md#SERV012), [TERM016 Language application](terminal_requirements.md#TERM016)

<a id="ZMC007"></a>

## 7.0 Callback requests _(ZMC007)_

The system shall let a terminal request a callback from an unavailable contact and notify the contact when available, without automatically calling.

> `zmala_terminal/common/tests/callbacks_live.py`

*Child links:* [TERM006 Callback confirmation](terminal_requirements.md#TERM006), [SERV008 Callback lifecycle](server_requirements.md#SERV008), [SERV009 Callback delivery](server_requirements.md#SERV009), [TERM015 Manual callback availability notice](terminal_requirements.md#TERM015), [SERV017 Callback email reminders](server_requirements.md#SERV017)

<a id="ZMC008"></a>

## 8.0 Remote maintenance _(ZMC008)_

Administration shall provide a command console for each terminal, with terminal polling, execution in its configured shell and returned results.

> `zmala_server/tests/console.test.js`

*Child links:* [SERV014 Maintenance queue and isolation](server_requirements.md#SERV014), [TERM021 Command execution](terminal_requirements.md#TERM021)

<a id="ZMC009"></a>

## 9.0 Administration and persistent state _(ZMC009)_

The server shall provide dark administration pages for accounts, groups, terminals, callbacks and activity and persist configuration and relevant history across restarts.

> `zmala_server/tests/admin.test.js`

*Child links:* [SERV010 Dark administration pages](server_requirements.md#SERV010), [SERV011 Selected terminal card](server_requirements.md#SERV011), [SERV015 State persistence and device isolation](server_requirements.md#SERV015)

<a id="ZMC010"></a>

## 10 Contact notifications and caller cancellation _(ZMC010)_

A caller ending an unanswered call shall stop terminal ringing and increase that contact's visible unread notification counter. Each phone text message received by the terminal shall increase the same counter without displaying its body or interrupting a call. The terminal shall show both per-contact counters and their combined total until each contact is acknowledged by opening their call or callback confirmation.

> `zmala_terminal/common/tests/callbacks_live.py`

*Child links:* [SERV006 Valid caller cancellation](server_requirements.md#SERV006), [TERM011 Caller hang-up while ringing](terminal_requirements.md#TERM011), [TERM012 Missed-call badge](terminal_requirements.md#TERM012), [TERM013 Missed-call acknowledgment](terminal_requirements.md#TERM013), [TERM014 Missed-call persistence](terminal_requirements.md#TERM014), [SERV016 Text message notifications](server_requirements.md#SERV016), [TERM023 Text messages use missed-call badges](terminal_requirements.md#TERM023)

