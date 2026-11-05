"""Versioned build intent and lab configuration, separate from package locks."""
import hashlib
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
artefact:
  version: unqualified-{role}-probe1
image:
  layer: image-rota
  name: zmala-{role}-boot-probe
  rootfs_type: ext4
  boot_part_size: 512M
  system_part_size: 8G
  data_part_size: 4G
layer:
  base: trixie-minbase
  eeprom_scope: zmala-probe-eeprom
packages:
  - rauc={profiles()['rauc_version']}
'''


def emit_lab(role, output):
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    # Requiring a project-local layer makes omission of -S fail during layer
    # resolution, rather than silently assembling an unmasked probe. Emit the
    # standalone hook with LF, including from Windows checkouts.
    layer = output/'layer'
    layer.mkdir()
    (layer/'zmala-probe-eeprom.yaml').write_text('''# METABEGIN
# X-Env-Layer-Name: zmala-probe-eeprom
# X-Env-Layer-Desc: Keep EEPROM updates outside diagnostic probe scope
# X-Env-Layer-Category: policy
# X-Env-Layer-Version: 1.0.0
# X-Env-Layer-Requires: trixie-minbase
# METAEND
---
''', encoding='utf-8', newline='\n')
    hooks = layer/'zmala-probe-eeprom.d/hooks'
    hooks.mkdir(parents=True)
    hook = hooks/'customize99-zmala-eeprom-scope'
    hook.write_text(Path(__file__).with_name('eeprom_policy.py').read_text(encoding='utf-8'),
                    encoding='utf-8', newline='\n')
    hook.chmod(0o755)
    (output/'probe.yaml').write_text(lab_config(role), encoding='utf-8', newline='\n')
    (output/'package-intent.txt').write_text('\n'.join(packages(role))+'\n', encoding='utf-8')
    (output/'status.json').write_text(json.dumps({
        'schema': 1, 'role': role, 'purpose': 'minimal-boot-probe',
        'production_eligible': False, 'application_installed': False,
        'packages_locked': False, 'hardware_qualified': False,
        'required_project_source': '.', 'eeprom_scope_hook_emitted': True,
        'blockers': ['boot-selector-commit', 'early-watchdog', 'package-lock',
                     'product-provisioning', 'data-mount-policy', 'hardware-qualification']
    }, indent=2)+'\n', encoding='utf-8')
    return output


def package_locks():
    """Verify reviewed intent/lock synchronization without network or binaries."""
    folder = ROOT/'build_tools/images/locks'
    index = json.loads((folder/'index.json').read_text())
    if (index['schema'] != 1 or index['purpose'] != 'requested-package-closure'
            or index['image_qualified'] is not False or set(index['roles']) != {'server', 'terminal'}):
        raise ValueError('Unknown role package lock index')
    for role, record in index['roles'].items():
        if record['file'] != role+'.json':
            raise ValueError('Unexpected role lock filename')
        path = folder/record['file']
        if path.stat().st_size > 4*1024**2 or path.is_symlink():
            raise ValueError('Invalid role package lock')
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != record['sha256']:
            raise ValueError('Role package lock digest changed')
        manifest = json.loads(body)
        if (manifest['requested'] != packages(role) or manifest['schema'] != 1
                or manifest['architecture'] != profiles()['architecture']
                or manifest['distribution'] != profiles()['distribution']
                or manifest['image_qualified'] is not False
                or len(manifest['packages']) != record['archives']
                or sum(p['bytes'] for p in manifest['packages']) != record['archive_bytes']):
            raise ValueError('Package intent and reviewed closure disagree; refresh intake through review')
    return index
