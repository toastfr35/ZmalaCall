"""Fullscreen HDMI test card for the opt-in TV plugin experiment tool."""
import argparse
from datetime import datetime
from pathlib import Path
import tkinter as tk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ready', type=Path, required=True)
    args = parser.parse_args()
    root = tk.Tk()
    root.title('ZmalaCall HDMI test card')
    # The Pi kiosk has no window manager to honour the fullscreen hint.
    root.overrideredirect(True)
    root.geometry(f'{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0')
    root.attributes('-fullscreen', True)
    root.attributes('-topmost', True)
    root.configure(cursor='none', bg='black')
    canvas = tk.Canvas(root, bg='black', highlightthickness=0)
    canvas.pack(fill='both', expand=True)

    def paint():
        width, height = canvas.winfo_width(), canvas.winfo_height()
        canvas.delete('all')
        colours = ('white', '#ffe000', '#00dddd', '#22cc55', '#dd22dd', '#ee3333', '#2255ee')
        for index, colour in enumerate(colours):
            canvas.create_rectangle(index * width / 7, 0, (index + 1) * width / 7, height, fill=colour, outline='')
        canvas.create_rectangle(width * .06, height * .18, width * .94, height * .82, fill='#101820', outline='white', width=8)
        canvas.create_text(width / 2, height * .32, text='ZmalaCall TV TEST', fill='white', font=('Sans', max(20, int(height / 12)), 'bold'))
        canvas.create_text(width / 2, height * .48, text='TERMINAL HDMI INPUT', fill='#66ff99', font=('Sans', max(16, int(height / 18)), 'bold'))
        canvas.create_text(width / 2, height * .64, text=datetime.now().strftime('%H:%M:%S'), fill='white', font=('Monospace', max(16, int(height / 16))))
        for x, y, text in [(0.08, .1, 'TOP LEFT'), (.92, .1, 'TOP RIGHT'), (.08, .9, 'BOTTOM LEFT'), (.92, .9, 'BOTTOM RIGHT')]:
            canvas.create_text(width*x, height*y, text=text, fill='black' if x < .5 else 'white', font=('Sans', max(12, int(height/40)), 'bold'))
        root.after(1000, paint)

    root.update()
    paint()
    root.update()
    args.ready.write_text('ready', encoding='ascii')
    root.mainloop()


if __name__ == '__main__':
    main()
