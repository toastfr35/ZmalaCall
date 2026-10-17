# Fictional sample portraits

These six new fictional people were generated with the built-in imagegen tool.
They share a square studio-portrait style: muted blue-gray background, soft natural
light, head-and-shoulders framing and a gentle smile. The names are fictional too.

| Account ID | Display name | Portrait |
|---|---|---|
| `term1` | Evelyn Brooks | [term1.png](term1.png) |
| `phone1` | Noah Bennett | [phone1.png](phone1.png) |
| `phone2` | Clara Reed | [phone2.png](phone2.png) |
| `phone3` | Gabriel Hayes | [phone3.png](phone3.png) |
| `phone4` | Mina Collins | [phone4.png](phone4.png) |
| `phone5` | Arthur Clarke | [phone5.png](phone5.png) |

`accounts.json` is the machine-readable name/portrait mapping. Account IDs and SIP
identities stay stable. These assets do not overwrite private live account data
unless explicitly imported. The application normalizes imported pictures to
480-pixel copies under its ignored `data/photos/` directory.

The previous portraits were preserved outside the repository on the development
PC. They are not included in this repository's new history.

See [generation prompts](additional-prompts.md) for the exact prompt set.
