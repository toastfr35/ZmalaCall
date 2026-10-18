# @test T-LLT-061
# @requirements LLR-TERM-REMOTE-017, LLR-TERM-REMOTE-020, LLR-TERM-UI-022, LLR-TERM-UI-024, LLR-TERM-HISTORY-017, LLR-TERM-POWER-017
# @environment native-sdk
# @plan Render real Pango/Cairo text and shared icon geometry into Pillow images, replacing only the Tk photo upload. Assert bounded dimensions, cache ownership, alpha/background composition and distinct power/battery/charging states. Exercise rounded corners, connectivity, Bluetooth, callback and capped missed-call badges, plus large transparent portraits in settled/moving modes. No display or camera is opened.
# @pass Pixel/dimension/cache assertions pass with Linux Pango/Cairo; unsupported hosts explicitly skip. Actual TV readability remains a separate visual check.
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image


class Photo:
    def __init__(self, image=None, **kwargs):
        self.image=(image if image is not None else Image.open(io.BytesIO(kwargs['data']))).convert('RGBA').copy()

    def width(self): return self.image.width
    def height(self): return self.image.height


@unittest.skipUnless(sys.platform.startswith('linux'),'Linux Pango/Cairo backend')
class LinuxRendererTests(unittest.TestCase):
    def setUp(self):
        from zmala_terminal.linux import text_renderer, icons
        self.text_module=text_renderer; self.icon_module=icons
        for patcher in (patch.object(text_renderer.tk,'PhotoImage',Photo),patch.object(text_renderer.ImageTk,'PhotoImage',Photo)):
            patcher.start(); self.addCleanup(patcher.stop)
        self.text=text_renderer.TextRenderer(None); self.icons=icons.IconRenderer(self.text)
        self.addCleanup(self.text.close)

    def test_unicode_wrapping_and_cache_keys_do_not_mix_styles(self):
        self.assertIsNone(self.text.photo('', 'Sans',20,'#000000','#ffffff',120))
        for text in ('Hello family '*15,'مرحبا بالعائلة '*15,'家族にこんにちは '*15):
            image=self.text.photo(text,'TkDefaultFont',18,'#123456','#ffffff',160)
            self.assertEqual(image.width(),160); self.assertGreater(image.height(),25)
            self.assertEqual(image.image.getpixel((0,0)),(18,52,86,255))
            self.assertIs(image,self.text.photo(text,'TkDefaultFont',18,'#123456','#ffffff',160))
            bold=self.text.photo(text,'TkDefaultFont',18,'#123456','#ffffff',160,True)
            self.assertIsNot(image,bold)
        small=self.text.photo('x','Sans',12,'#000000','#ffffff',0,rtl=True)
        self.assertEqual(small.width(),16)
        self.assertLessEqual(self.text.cache.bytes_used,self.text.cache.max_bytes)
        self.text.close(); self.assertEqual(len(self.text.cache),0)

    def test_portrait_scaling_alpha_and_background_cache_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'portrait.png'; Image.new('RGBA',(1800,900),(255,0,0,128)).save(path)
            settled=self.text.portrait(path,240,'#0000ff')
            self.assertEqual((settled.width(),settled.height()),(240,120))
            self.assertIs(settled,self.text.portrait(path,240,'#0000ff'))
            self.assertEqual(settled.image.getpixel((120,60)),(128,0,127,255))
            moving=self.text.portrait(path,240,'#0000ff',True)
            self.assertEqual(moving.image.getpixel((120,60)),(128,0,127,255))
            self.text.portrait(path,256,'#0000ff',True)
            self.assertEqual(len(self.text.backgrounds),1)
            self.text.portrait(path,240,'#00ff00',True)
            self.assertEqual(len(self.text.backgrounds),2)
            self.assertEqual([image.size for image in self.text.sources[str(path)]],[(1200,600),(460,230)])
            self.text.close()
            for cache in (self.text.portraits,self.text.sources,self.text.backgrounds): self.assertEqual(len(cache),0)

    def test_rounded_buttons_keep_background_corners_and_exact_dimensions(self):
        image=self.icons.rounded_button(200,60,'#00ff00','#000000')
        self.assertEqual((image.width(),image.height()),(200,60))
        self.assertEqual(image.image.getpixel((0,0)),(0,0,0,255))
        self.assertEqual(image.image.getpixel((100,30)),(0,255,0,255))
        self.assertIs(image,self.icons.rounded_button(200,60,'#00ff00','#000000'))
        narrow=self.icons.rounded_button(10,8,'#00ff00','#000000')
        self.assertEqual((narrow.width(),narrow.height()),(10,8))

    def test_power_battery_bluetooth_and_badges_are_distinguishable_and_capped(self):
        with patch.object(self.icon_module,'layout_for',wraps=self.icon_module.layout_for) as layout:
            power=[self.icons.usb_power(value,'#0d121c') for value in (True,False,None)]
            self.assertEqual(len({photo.image.tobytes() for photo in power}),3)
            batteries=[self.icons.battery(value,'#0d121c') for value in (None,0,10,20,25,100,200)]
            self.assertEqual(batteries[-1].image.tobytes(),batteries[-2].image.tobytes())
            self.assertNotEqual(batteries[2].image.tobytes(),batteries[3].image.tobytes())
            charging=self.icons.battery(10,'#0d121c',True)
            self.assertNotEqual(charging.image.tobytes(),batteries[2].image.tobytes())
            connected=self.icons.bluetooth(22,'#71ddba','#0d121c',True)
            disconnected=self.icons.bluetooth(22,'#71ddba','#0d121c',False)
            self.assertNotEqual(connected.image.tobytes(),disconnected.image.tobytes())
            for count in (0,1,42,100):
                badge=self.icons.missed_call(22,'#ff0000','#ffffff',count)
                self.assertEqual(badge.width(),64 if count else 48)
            labels=[c.args[1] for c in layout.call_args_list]
            self.assertIn('?',labels); self.assertIn('1',labels); self.assertIn('42',labels); self.assertIn('99+',labels)
        callback=self.icons.callback(20,'#ff0000','#ffffff')
        self.assertEqual((callback.width(),callback.height()),(44,44))
        network=self.icons.connectivity(168,30,['#ff0000','#00ff00','#0000ff'],'#0d121c')
        self.assertEqual((network.width(),network.height()),(168,30))
        self.assertLessEqual(self.icons.cache.bytes_used,self.icons.cache.max_bytes)
