"""Small Windows GUI for checking, confirming and deploying a Pi terminal."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
import traceback

from backend import Deployment, verify_payload


def resources():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1] / 'dist'


def logo_path():
    if getattr(sys, 'frozen', False):
        return resources() / 'zmala-icon.png'
    return Path(__file__).resolve().parents[2] / 'zmala_terminal/common/assets/zmala-icon.png'


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Zmala terminal setup')
        self.geometry('820x660')
        self.minsize(780, 640)
        self.configure(bg='#f3f6fa')
        self.events = queue.Queue()
        self.busy = False
        self.target = None
        self.archive = resources() / 'ZmalaCall-Terminal-rpi.tar.gz'
        logs = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ZmalaCall' / 'Installer' / 'logs'
        logs.mkdir(parents=True, exist_ok=True)
        self.log_path = logs / ('install-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.log')
        self.log_file = self.log_path.open('w', encoding='utf-8')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background='#f3f6fa')
        style.configure('Card.TFrame', background='#ffffff')
        style.configure('TLabel', background='#f3f6fa', foreground='#192c43', font=('Segoe UI', 11))
        style.configure('Title.TLabel', font=('Segoe UI', 25, 'bold'))
        style.configure('Muted.TLabel', foreground='#56677b', font=('Segoe UI', 10))
        style.configure('Card.TLabel', background='#ffffff')
        style.configure('CardTitle.TLabel', background='#ffffff', font=('Segoe UI', 13, 'bold'))
        style.configure('CardNote.TLabel', background='#ffffff', foreground='#56677b', font=('Segoe UI', 10))
        style.configure('TEntry', padding=10, fieldbackground='#ffffff', bordercolor='#c8d4e1')
        style.configure('TButton', font=('Segoe UI', 11), padding=(18, 11), background='#e5edf5', borderwidth=0)
        style.configure('Primary.TButton', background='#1769aa', foreground='#ffffff', font=('Segoe UI', 11, 'bold'))
        style.map('Primary.TButton', background=[('disabled', '#dce5ee'), ('active', '#12558b')],
                  foreground=[('disabled', '#78889a')])
        style.configure('Horizontal.TProgressbar', background='#1769aa', troughcolor='#e8eef5', borderwidth=0)
        frame = ttk.Frame(self, padding=28)
        frame.pack(fill='both', expand=True)
        hero = ttk.Frame(frame)
        hero.pack(fill='x')
        self.logo = tk.PhotoImage(file=str(logo_path())).subsample(4)
        self.iconphoto(True, self.logo)
        ttk.Label(hero, image=self.logo).pack(side='left', padx=(0, 16))
        titles = ttk.Frame(hero)
        titles.pack(side='left')
        ttk.Label(titles, text='Set up your Zmala terminal', style='Title.TLabel').pack(anchor='w')
        ttk.Label(titles, text='Raspberry Pi 4 · Argon ONE V2', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
        steps = ttk.Frame(frame)
        steps.pack(fill='x', pady=(24, 22))
        self.steps = []
        for label in ('1   Check Pi', '2   Install', '3   Ready'):
            item = tk.Label(steps, text=label, font=('Segoe UI', 11, 'bold'), padx=12, pady=10)
            item.pack(side='left', fill='x', expand=True, padx=(0, 4))
            self.steps.append(item)
        self.set_step(0)
        connection = ttk.Frame(frame, style='Card.TFrame', padding=20)
        connection.pack(fill='x')
        ttk.Label(connection, text='Connect your Pi', style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(connection, text='Use the SD card prepared with the guide. Connect power, Ethernet and the TV.',
                  style='CardNote.TLabel', wraplength=680).pack(anchor='w', pady=(5, 14))
        row = ttk.Frame(connection, style='Card.TFrame')
        row.pack(fill='x')
        ttk.Label(row, text='Network address', style='Card.TLabel').pack(side='left', padx=(0, 18))
        self.host = tk.StringVar(value='zmala.local')
        self.entry = ttk.Entry(row, textvariable=self.host, font=('Segoe UI', 11))
        self.entry.pack(side='left', fill='x', expand=True)
        self.host.trace_add('write', self.invalidate)
        ttk.Label(connection, text='The hostname is zmala. Use zmala.local here, or its Ethernet IP address.',
                  style='CardNote.TLabel', wraplength=680).pack(anchor='w', pady=(10, 0))
        status_card = ttk.Frame(frame, style='Card.TFrame', padding=20)
        status_card.pack(fill='both', expand=True, pady=(14, 18))
        self.status_heading = tk.StringVar(value='Ready when you are')
        ttk.Label(status_card, textvariable=self.status_heading, style='CardTitle.TLabel').pack(anchor='w')
        self.status = tk.StringVar(value='Check the connection and operating system first. Installation starts only after you confirm.')
        ttk.Label(status_card, textvariable=self.status, style='CardNote.TLabel', wraplength=670).pack(anchor='w', pady=(8, 14))
        self.progress = ttk.Progressbar(status_card, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 12))
        ttk.Label(status_card, text='Automatic fan setup · Reboot and startup checks included',
                  style='CardNote.TLabel', wraplength=670).pack(anchor='w')
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.check_button = ttk.Button(actions, text='1. Check Pi', command=self.check)
        self.check_button.pack(side='left')
        self.install_button = ttk.Button(actions, text='2. Install…', style='Primary.TButton', command=self.confirm, state='disabled')
        self.install_button.pack(side='left', padx=10)
        ttk.Button(actions, text='View details', command=self.show_details).pack(side='right')
        self.details = tk.Toplevel(self)
        self.details.title('Zmala setup details')
        self.details.geometry('780x450')
        self.details.withdraw()
        self.details.protocol('WM_DELETE_WINDOW', self.details.withdraw)
        self.output = scrolledtext.ScrolledText(self.details, bg='#101a2b', fg='#e1e9f3',
                                              font=('Consolas', 10), wrap='word', state='disabled', padx=14, pady=14)
        self.output.pack(fill='both', expand=True)
        ttk.Button(self.details, text='Open saved log', command=lambda: os.startfile(self.log_path)).pack(anchor='e', padx=12, pady=10)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.drain_timer = self.after(100, self.drain)

    def set_step(self, active):
        for index, label in enumerate(self.steps):
            label.configure(bg='#1769aa' if index == active else '#e5edf5',
                            fg='#ffffff' if index == active else '#56677b')

    def show_details(self):
        self.details.deiconify()
        self.details.lift()

    def invalidate(self, *_):
        if not self.busy and self.target is not None:
            self.target.close()
            self.target = None
            self.install_button.configure(state='disabled')
            self.set_step(0)
            self.status_heading.set('Check the new address')
            self.status.set('Address changed. Check this Pi before installing.')

    def emit(self, text):
        self.events.put(('log', text))

    def write_log(self, text):
        self.log_file.write(text)
        self.log_file.flush()
        self.output.configure(state='normal')
        self.output.insert('end', text)
        self.output.see('end')
        self.output.configure(state='disabled')

    def start(self, work, completion):
        self.busy = True
        for widget in (self.entry, self.check_button, self.install_button):
            widget.configure(state='disabled')
        self.progress.start(12)
        def worker():
            try:
                result = work()
                self.events.put((completion, result))
            except Exception as error:
                self.emit(traceback.format_exc())
                self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def check(self):
        if self.target:
            self.target.close()
        try:
            self.target = Deployment(self.host.get(), self.emit)
        except Exception as error:
            messagebox.showerror('Cannot check Pi', str(error), parent=self)
            return
        self.status.set('Checking connection and compatibility…')
        self.status_heading.set('Checking your Pi')
        self.set_step(0)
        def work():
            verify_payload(self.archive)
            return self.target.check()
        self.start(work, 'checked')

    # @llr LLR-TERM-INSTALL-003
    def confirm(self):
        info = self.target.info
        action = 'Update' if info['installed'] else 'Install'
        answer = messagebox.askokcancel('Confirm installation',
            f"{action} ZmalaCall on {self.host.get()}?\n\n"
            f"{info['model']}\n{info['os'].get('PRETTY_NAME')} (64-bit)\n"
            f"Ethernet address: {info['ssh_address']}\n\n"
            'This will install dependencies and automatic startup, restrict SSH to Ethernet, '
            'set the boot screen, reduce SD writes using RAM logs/swap, and reboot the Pi.\n'
            'Existing enrollment is preserved. Keep power and Ethernet connected.\n\n'
            'Argon ONE fan control is included automatically.\n'
            f"SSH identity:\n{self.target.key}", parent=self)
        if not answer:
            return
        self.status.set('Installing — leave the Pi powered and connected…')
        self.status_heading.set('Setting up your terminal')
        self.set_step(1)
        self.start(lambda: self.target.install(self.archive, True), 'installed')

    def drain(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.write_log(value)
                    continue
                self.busy = False
                self.progress.stop()
                for widget in (self.entry, self.check_button):
                    widget.configure(state='normal')
                if kind == 'checked':
                    self.install_button.configure(state='normal')
                    self.status_heading.set('Your Pi is ready to install')
                    self.set_step(1)
                    self.status.set(f"Checks passed: {value['model']} · {value['ssh_address']}. Ready for confirmation.")
                elif kind == 'installed':
                    self.status_heading.set('Your terminal is ready')
                    self.set_step(2)
                    self.status.set('Complete — terminal running after reboot. Continue setup on the TV.')
                    self.target.close()
                    self.target = None
                    messagebox.showinfo('Installation complete', 'ZmalaCall is running on the Pi.\n'
                                        'Follow the remote and QR setup instructions on the TV.', parent=self)
                else:
                    self.status_heading.set('We need your attention')
                    self.status.set('Setup could not finish. View details for the error and use Open saved log to keep a copy.')
                    if self.target:
                        self.target.close()
                        self.target = None
                    messagebox.showerror('Installation needs attention', value + '\n\nLog: ' + str(self.log_path), parent=self)
        except queue.Empty:
            pass
        self.drain_timer = self.after(100, self.drain)

    def close(self):
        if self.busy:
            messagebox.showinfo('Work in progress', 'Please wait for the current check or installation to finish.', parent=self)
            return
        if self.target:
            self.target.close()
        self.log_file.close()
        self.after_cancel(self.drain_timer)
        self.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', type=Path, help='Write bundled resource/UI diagnostics and exit')
    parser.add_argument('--smoke-host', help='Also perform read-only SSH checks during the smoke test')
    args = parser.parse_args()
    if args.smoke_host and not args.smoke_test:
        parser.error('--smoke-host requires --smoke-test')
    app = Installer()
    if args.smoke_test:
        # Build verification only: installation cannot run through this path.
        try:
            verify_payload(app.archive)
            app.update()
            result = 'GUI initialized; bundled package checksum verified.\n'
            if args.smoke_host:
                target = Deployment(args.smoke_host, app.write_log)
                try:
                    target.check()
                    result += 'Bundled SSH and target preflight checks passed.\n'
                finally:
                    target.close()
            args.smoke_test.write_text(result, encoding='utf-8')
        except Exception:
            args.smoke_test.write_text(traceback.format_exc(), encoding='utf-8')
            app.close()
            raise
        app.after(200, app.close)
    app.mainloop()


if __name__ == '__main__':
    main()
