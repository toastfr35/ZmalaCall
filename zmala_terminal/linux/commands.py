"""POSIX shell command construction."""
import shutil

# @llr TLLR100
def command_arguments(command, shell, batch_directory=None):
    if shell not in ('sh', 'bash'):
        raise ValueError('Choose sh or bash in the Linux terminal account settings')
    executable = shutil.which(shell)
    if not executable:
        raise FileNotFoundError(f'{shell} is not installed on this terminal')
    return [executable, '-c', command]
