"""Idempotent Raspberry Pi boot branding; preserve root/disk/network arguments."""
from pathlib import Path


# @llr TLLR004
def quiet_command_line(text):
    tokens = [token for token in text.split() if token not in ('console=tty1', 'quiet', 'splash', 'plymouth.ignore-serial-consoles')
              and not token.startswith(('loglevel=', 'logo.nologo', 'vt.global_cursor_default='))]
    return ' '.join(tokens + ['quiet', 'splash', 'plymouth.ignore-serial-consoles',
                             'loglevel=3', 'logo.nologo', 'vt.global_cursor_default=0']) + '\n'


def main():
    boot = Path('/boot/firmware')
    cmdline = boot / 'cmdline.txt'
    config = boot / 'config.txt'
    for path in (cmdline, config):
        backup = path.with_suffix(path.suffix + '.before-zmala')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    cmdline.write_text(quiet_command_line(cmdline.read_text()))
    marker = '# ZmalaCall boot logo'
    content = config.read_text()
    if marker not in content:
        config.write_text(content.rstrip() + '\n\n[all]\n' + marker + '\ndisable_splash=1\n')


if __name__ == '__main__':
    main()
