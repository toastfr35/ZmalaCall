# @test T-HLT-044
# @requirements HLR-TERM-UI-027
# @environment display
# @plan Render every locale/state with Pango at 900x620 and 1280x720, assert text bounds, and keep the independent progress process alive while a disposable app exits. Inspect real Tk mapped/hidden window state through a test-only process observer.
# @pass All text fits and the progress window survives application exit; idle withdraws it. Tests render under Xvfb and do not claim real TV power/source qualification.
import os
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import unittest
from zmala_terminal.linux.update_screen import MESSAGES,STATES,message,render_message

@unittest.skipUnless(sys.platform=='linux' and os.environ.get('DISPLAY'),'Linux Pango/X11 display')
class UpdateScreenTests(unittest.TestCase):
    def test_all_locales_fit_and_independent_window_survives_app_exit(self):
        for width,height in ((900,620),(1280,720)):
            for language in MESSAGES:
                for phase in STATES:
                    png,(w,h)=render_message(message(language,phase),language,width,height)
                    self.assertTrue(png.startswith(b'\x89PNG'));self.assertLessEqual(w,width*.81);self.assertLessEqual(h,height*.65)
        with tempfile.TemporaryDirectory() as folder:
            state=Path(folder)/'state';state.write_text(json.dumps({'phase':'updating','language':'fr'}))
            evidence=Path(folder)/'evidence'
            script="""import tkinter as tk,json,sys
from pathlib import Path
from zmala_terminal.linux.update_screen import main
original=tk.Tk
def construct():
 root=original()
 def inspect():
  root.update_idletasks()
  Path(sys.argv[2]).write_text(json.dumps({'mapped':bool(root.winfo_ismapped()),'image':str(getattr(root,'image',''))}))
  root.after(100,inspect)
 root.after(100,inspect)
 return root
tk.Tk=construct
main(sys.argv[1])
"""
            display=subprocess.Popen([sys.executable,'-c',script,str(state),str(evidence)],stderr=subprocess.PIPE)
            app=subprocess.Popen([sys.executable,'-c','pass'])
            def wait_for(predicate):
                end=time.monotonic()+10
                while time.monotonic()<end:
                    try:value=predicate()
                    except (OSError,ValueError):value=None
                    if value:return value
                    if display.poll() is not None:raise AssertionError(display.stderr.read().decode())
                    time.sleep(.1)
                raise AssertionError('Display state timeout')
            def window():return json.loads(evidence.read_text())
            try:
                initial=wait_for(lambda:window() if window()['mapped'] else None)
                app.wait(timeout=5);self.assertIsNone(display.poll())
                state.write_text(json.dumps({'phase':'rollback','language':'ar'}));time.sleep(.6)
                wait_for(lambda:window()['mapped'] and window()['image'] != initial['image'])
                state.write_text(json.dumps({'phase':'idle','language':'ar'}))
                wait_for(lambda:not window()['mapped'])
            finally:
                display.terminate()
                try:display.wait(timeout=5)
                except subprocess.TimeoutExpired:display.kill();display.wait(timeout=5)
                display.stderr.close()
                if app.poll() is None:app.kill();app.wait(timeout=5)
