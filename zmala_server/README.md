# Zmala Server

Node server and browser administration. The entry point is `main.js`.

| Responsibility | Source |
| --- | --- |
| HTTP boundary | `http/` routes and authentication, `validation.js` field admission |
| State | `store.js`, `accounts.js`, `snapshot-file.js` and backup modules |
| Calls | `sip-server.js`, SIP helpers and `media.js` |
| Browser UI | `web/admin-*.js` and `web/styles/`; generated `admin.js`/`admin.css` are rebuilt |

Run `npm run build:admin` after editing browser source. Runtime deployment and image assembly remain outside this directory.

Read the [implementation guide](../docs/server.md) and
[development setup](../docs/development.md). Product requirements are in
[`requirements/server/`](../requirements/server/); unit and system plans are in
[`tests/server/`](../tests/server/).

Run from the repository root after installing the development dependencies:

```sh
make test
make requirements
```
