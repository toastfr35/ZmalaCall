"""Check native Tk layout and engine startup without OS input automation."""
import json
import argparse
import copy
import sys
from pathlib import Path
import time

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.main import Terminal
from zmala_terminal.common.model import State

parser = argparse.ArgumentParser()
parser.add_argument('--bootstrap', type=Path, default=ROOT / 'data/terminal.json')
parser.add_argument('--profile', default='terminal')
args = parser.parse_args()
terminal = Terminal(bootstrap=args.bootstrap.resolve(), profile=args.profile)
deadline = time.monotonic() + 7
try:
    while time.monotonic() < deadline:
        terminal.root.update()
        time.sleep(.02)
    assert terminal.engine and terminal.engine.registered, 'Terminal did not register'
    result = []
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    assert not any(w.winfo_class() in ('Button', 'TButton') for w in descendants(terminal.root)), 'Terminal has on-screen buttons'
    original = copy.deepcopy(terminal.model.config)
    contact = original['contacts'][0]
    terminal.model.config['contacts'] = [dict(contact, id='alice', name='Alice', can_call=True), dict(contact, id='bob', name='Bob', can_call=True), dict(contact, id='carol', name='Carol', can_call=True)]
    terminal.render()
    terminal.root.update_idletasks()
    assert len(terminal.model.carousel) == 3 and terminal.model.carousel[1]['id'] == terminal.model.selected['id']
    assert terminal.current_photos, 'Account pictures were not rendered'
    terminal.model.button('right')
    terminal.render()
    assert terminal.model.carousel[1]['id'] == 'bob'
    assert terminal.connectivity.find_withtag('network-status'), 'Connection graphic is missing'
    terminal.draw_connectivity(True)
    assert terminal.connectivity.find_withtag('network-status'), 'Cached connection graphic disappeared'
    for state in [State.HOME, State.RINGING, State.CALLING, State.CONNECTING, State.IN_CALL, State.STOPPING]:
        terminal.model.state = state
        terminal.model.contact = terminal.model.selected if state != State.HOME else None
        terminal.render()
        terminal.root.update_idletasks()
        bounds = {}
        for name in ['title', 'name', 'subtitle', 'connectivity', 'avatar', 'video']:
            w = getattr(terminal, name)
            if not w.winfo_ismapped():
                continue
            x, y = w.winfo_rootx() - terminal.root.winfo_rootx(), w.winfo_rooty() - terminal.root.winfo_rooty()
            width, height = w.winfo_width(), w.winfo_height()
            bounds[name] = [x, y, width, height]
            assert x >= 0 and y >= 0 and x + width <= terminal.root.winfo_width() + 1 and y + height <= terminal.root.winfo_height() + 1, (state, name, bounds[name])
        result.append({'state':state.value,'bounds':bounds})
    (ROOT / 'data/ui-smoke-result.json').write_text(json.dumps(result, indent=2))
    terminal.model.configure(original)
    terminal.model.state = State.HOME
    terminal.model.contact = None
    terminal.root.geometry('900x620')
    terminal.render()
    terminal.root.update()
    terminal.root.update_idletasks()
    for widget in [terminal.title,terminal.avatar,terminal.name,terminal.subtitle]:
        x,y=widget.winfo_rootx()-terminal.root.winfo_rootx(),widget.winfo_rooty()-terminal.root.winfo_rooty()
        assert x>=0 and y>=0 and x+widget.winfo_width()<=terminal.root.winfo_width()+1 and y+widget.winfo_height()<=terminal.root.winfo_height()+1, (str(widget),[x,y,widget.winfo_width(),widget.winfo_height()],[terminal.root.winfo_width(),terminal.root.winfo_height()])
    print('Native terminal registered; carousel, pictures, button-free dark layout and connectivity graphic passed at both window sizes.')
finally:
    terminal.close()
