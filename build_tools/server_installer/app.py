"""Windows server setup with explicit target check and installation confirmation."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from build_tools.server_installer.backend import Deployment, verify_payload
from build_tools.server_installer.cli import resources


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Zmala server setup')
        self.geometry('800x680')
        self.minsize(760, 650)
        self.configure(bg='#f3f6fa')
        self.target, self.busy = None, False
        self.events = queue.Queue()
        logs = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'ZmalaCall/ServerInstaller'
        logs.mkdir(parents=True, exist_ok=True)
        self.log = (logs/('setup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.log')).open('w', encoding='utf-8')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#f3f6fa')
        style.configure('TLabel', background='#f3f6fa', foreground='#192c43', font=('Segoe UI', 11))
        style.configure('Title.TLabel', font=('Segoe UI', 26, 'bold'))
        style.configure('TButton', padding=(16, 10), font=('Segoe UI', 11))
        style.configure('Primary.TButton', background='#1769aa', foreground='white')
        style.configure('TEntry', padding=8)
        frame = ttk.Frame(self, padding=28)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Set up your Zmala server', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Raspberry Pi 3 / 4 · Raspberry Pi OS Lite 64-bit', foreground='#56677b').pack(anchor='w', pady=(5, 20))
        ttk.Label(frame, text='Connect power and Ethernet to the Pi prepared with Raspberry Pi Imager.\nNo screen or keyboard is needed.', wraplength=710).pack(anchor='w')
        ttk.Label(frame, text='Network address').pack(anchor='w', pady=(22, 5))
        self.host = tk.StringVar(value='zmalaserver.local')
        self.entry = ttk.Entry(frame, textvariable=self.host)
        self.entry.pack(fill='x')
        self.host.trace_add('write', self.invalidate)
        ttk.Label(frame, text='Optional: import existing server data').pack(anchor='w', pady=(18, 5))
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.data = tk.StringVar()
        self.data_entry = ttk.Entry(row, textvariable=self.data)
        self.data_entry.pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(row, text='Choose folder…', command=self.choose)
        self.browse.pack(side='left', padx=(8, 0))
        ttk.Label(frame, text='Leave blank for a new server. Imports accounts, settings, portraits and credentials.\nExisting Pi server data is preserved on updates.', wraplength=710, foreground='#56677b').pack(anchor='w', pady=(7, 18))
        self.status = tk.StringVar(value='1  Check the Pi     →     2  Confirm installation     →     3  Ready')
        ttk.Label(frame, textvariable=self.status, wraplength=710).pack(anchor='w', pady=(0, 12))
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x')
        self.output = scrolledtext.ScrolledText(frame, height=9, bg='#101a2b', fg='#e1e9f3',
                                              font=('Consolas', 10), state='disabled', wrap='word')
        self.output.pack(fill='both', expand=True, pady=16)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.check_button = ttk.Button(actions, text='1. Check Pi', command=self.check)
        self.check_button.pack(side='left')
        self.install_button = ttk.Button(actions, text='2. Install…', style='Primary.TButton', command=self.confirm, state='disabled')
        self.install_button.pack(side='left', padx=10)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.drain)

    def choose(self):
        value = filedialog.askdirectory(parent=self, title='Select the existing zmala_server/data folder')
        if value:
            self.data.set(value)

    def invalidate(self, *_):
        if not self.busy and self.target:
            self.target.close()
            self.target = None
            self.install_button.configure(state='disabled')

    def emit(self, message):
        self.events.put(('log', message))

    def start(self, action, complete):
        self.busy = True
        for item in (self.entry, self.data_entry, self.browse, self.check_button, self.install_button):
            item.configure(state='disabled')
        self.progress.start()
        def worker():
            try:
                action()
                self.events.put((complete, ''))
            except Exception as error:
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def check(self):
        self.invalidate()
        try:
            self.target = Deployment(self.host.get(), self.emit)
        except Exception as error:
            messagebox.showerror('Check failed', str(error), parent=self)
            return
        self.status.set('Checking connection, OS, Ethernet and available storage…')
        def work():
            verify_payload(resources()/'ZmalaCall-Server-rpi.tar.gz')
            self.target.check()
        self.start(work, 'checked')

    # @llr SLLR091
    def confirm(self):
        info = self.target.info
        migration = self.data.get().strip()
        text = (f"Install on {info['hostname']} ({info['ssh_address']})?\n\n{info['model']}\n"
                f"{info['os'].get('PRETTY_NAME')}\n\n"
                'Install the server and automatic startup, restrict SSH to Ethernet, '
                'use RAM logs and swap, then reboot and verify. SSH stays enabled.\n\n'
                + ('Import data from:\n'+migration+'\n\n' if migration else '')
                + 'SSH identity:\n'+self.target.key)
        if messagebox.askokcancel('Confirm server installation', text, parent=self):
            self.status.set('Installing — keep power and Ethernet connected…')
            self.start(lambda: self.target.install(resources()/'ZmalaCall-Server-rpi.tar.gz', migration or None), 'installed')

    def drain(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'log':
                self.log.write(value)
                self.log.flush()
                self.output.configure(state='normal')
                self.output.insert('end', value)
                self.output.see('end')
                self.output.configure(state='disabled')
                continue
            self.busy = False
            self.progress.stop()
            for item in (self.entry, self.data_entry, self.browse, self.check_button):
                item.configure(state='normal')
            if kind == 'checked':
                self.status.set('Checks passed. Ready for your installation confirmation.')
                self.install_button.configure(state='normal')
            elif kind == 'installed':
                self.status.set('Server ready at http://'+self.target.wired_address+':8080/')
                self.invalidate()
            else:
                self.emit('FAILED: '+value+'\n')
                self.status.set('Installation stopped. See the details below.')
                messagebox.showerror('Setup stopped', value, parent=self)
                self.invalidate()
        self.after(100, self.drain)

    def close(self):
        if self.busy:
            messagebox.showinfo('Installation in progress', 'Wait for the current operation to finish.', parent=self)
            return
        if self.target:
            self.target.close()
        self.log.close()
        self.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', type=Path)
    args = parser.parse_args()
    app = Installer()
    if args.smoke_test:
        app.withdraw()
        app.update_idletasks()
        verify_payload(resources()/'ZmalaCall-Server-rpi.tar.gz')
        args.smoke_test.write_text('GUI initialized; bundled server package checksum verified.\n')
        app.close()
    else:
        app.mainloop()
    return 0
