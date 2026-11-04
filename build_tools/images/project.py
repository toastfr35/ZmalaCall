"""Versioned build intent and lab configuration, separate from package locks."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def profiles():
    value = json.loads((ROOT/'build_tools/images/profiles.json').read_text())
    if (value['schema'] != 1 or value['architecture'] != 'arm64'
            or value['distribution'] != 'trixie' or value['board'] != 'pi4'
            or value['qualification'] != 'development-only'
            or set(value['roles']) != {'server', 'terminal'}):
        raise ValueError('Unknown or unqualified build profile')
    return value


def packages(role):
    profile = profiles()
    config = profile['roles'][role]
    result = {'rauc='+profile['rauc_version'], 'dbus', 'systemd', 'ca-certificates'}
    if 'packages_file' in config:
        result.update(line.strip() for line in (ROOT/config['packages_file']).read_text().splitlines()
                      if line.strip() and not line.startswith('#'))
    result.update(config['extra_packages'])
    if not all(re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?:=[A-Za-z0-9:+.~-]+)?', p) for p in result):
        raise ValueError('Invalid package name/version')
    return sorted(result)


def lab_config(role):
    """Minimal boot probe only: deliberately no production application or RAUC activation.

    Upstream image-rota's mutable /var and selector policy are not adopted as
    production design. This output exists to establish hardware boot feasibility.
    Role package intent is emitted separately for later locked image builds.
    """
    profiles()['roles'][role]
    return f'''# Development boot probe; not a Zmala installer or update candidate.
# Package resolution is not locked. Never publish to a stable image/feed.
device:
  layer: rpi4
image:
  layer: image-rota
  name: zmala-{role}-boot-probe
  rootfs_type: ext4
  boot_part_size: 512M
  system_part_size: 8G
  data_part_size: 4G
layer:
  base: trixie-minbase
packages:
  - rauc={profiles()['rauc_version']}
'''


def emit_lab(role, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    (output/'probe.yaml').write_text(lab_config(role), encoding='utf-8', newline='\n')
    (output/'package-intent.txt').write_text('\n'.join(packages(role))+'\n', encoding='utf-8')
    (output/'status.json').write_text(json.dumps({
        'schema': 1, 'role': role, 'purpose': 'minimal-boot-probe',
        'production_eligible': False, 'application_installed': False,
        'packages_locked': False, 'hardware_qualified': False,
        'blockers': ['boot-selector-commit', 'early-watchdog', 'package-lock',
                     'product-provisioning', 'data-mount-policy', 'hardware-qualification']
    }, indent=2)+'\n', encoding='utf-8')
    return output
