# @test T-HLT-036
# @requirements HLR-TERM-UI-012
# @environment display
# @plan Render a synthetic two-colour GIF through the real terminal fixture and controller. Check the selected canvas image changes, holds its last frame through redraw, replays on reselection and cancels/clears its cache for a call transition. No live SIP/camera/TV is used.
# @pass Actual Tk pixels and controller state meet all assertions; no hardware-call qualification is claimed.
"""Real selected-card GIF integration with an isolated enrollment/configuration."""
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tests.support.terminal.ui_fixture import terminal_fixture,pump
from tests.support.terminal.portrait_fixture import make_gif
from zmala_terminal.common.model import State
from zmala_terminal.common.ui import carousel

def exercise():
    with terminal_fixture() as (app,directory), patch.object(carousel,'ROOT',directory):
        data=directory/'data';data.mkdir(exist_ok=True)
        photo=make_gif(data)
        config=app.model.config.copy();person=config['contacts'][0]
        config['contacts']=[person|{'photo':photo},config['contacts'][1]]
        app.model.configure(config);app.render()
        player=app.portrait_animation
        # The display runner adds an outer disposable ROOT; this fixture owns
        # the synthetic portrait path and explicitly supplies that data directory.
        player.directory=data
        pump(app,lambda:player.completed==1,timeout=10)
        last=app.avatar.find_withtag('portrait-preview-target')[-1]
        image=app.avatar.itemcget(last,'image')
        assert app.root.tk.call(image,'get',200,200)==(0,0,255)
        app.render();pump(app,lambda:app.avatar.itemcget(app.avatar.find_withtag('portrait-preview-target')[-1],'image')==image)
        assert player.completed==1
        app.press('right');pump(app,lambda:player.key is None)
        app.press('left')
        app.root.after(600,lambda:(setattr(app,'carousel_motion',None),app.render()))
        pump(app,lambda:player.completed==2,timeout=10)
        app.model.state=State.IN_CALL;pump(app,lambda:not player.cache)
        assert not player.playing and not player.error_count
        print('Animated portrait display checks passed.')
if __name__=='__main__':exercise()
