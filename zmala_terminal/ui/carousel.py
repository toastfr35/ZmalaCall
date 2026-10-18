"""Carousel portraits and notification icons. The controller owns state and renderer lifetime."""
import math
import time
import tkinter as tk
from model import State
from carousel import CarouselLayout, carousel_contacts
from configuration import ROOT
from theme import BG, FG, MUTED, GREEN, RED, PANEL, ACCENT, BADGE_RED, BADGE_WHITE


class CarouselView:
    def draw_avatar(self, contact):
        width, height = max(700, self.avatar.winfo_width()), max(120, self.avatar.winfo_height())
        signature = (width, height, self.language, repr(contact)) if self.model.state == State.RINGING else None
        if signature and signature == getattr(self, 'ring_signature', None):
            self.animate_ringing(time.monotonic())
            return
        self.ring_signature = signature
        previous_items = self.avatar.find_all()
        self.current_photos = []
        self.current_text_images = []
        center_x, center_y = width / 2, height / 2
        idle = self.model.state == State.HOME
        layout = CarouselLayout.fit(width, height, len(self.model.contacts),
                                    (self.model.config or {}).get('carousel_portraits', 3))
        if self.model.state == State.RINGING:
            if self.ringing_started is None:
                self.ringing_started = time.monotonic()
            for index in range(2):
                self.avatar.create_oval(0, 0, 1, 1, outline=GREEN, width=3,
                                        tags=('ring-pulse', 'ring-pulse-'+str(index)))
        else:
            self.ringing_started = None
        if idle and self.carousel_motion:
            cards = self.carousel_motion.frames(time.monotonic(), layout.slots)
        else:
            if not idle:
                self.carousel_motion = None
            people = carousel_contacts(self.model.contacts, self.model.index, layout.slots) if idle else [None, contact, None]
            center = len(people)//2
            cards = [(person, float(index-center)) for index, person in enumerate(people) if idle or index == center]
        # Draw the larger cards last so overlapping moving cards remain legible.
        for person, slot in sorted(cards, key=lambda card: abs(card[1]), reverse=True):
            self.draw_card(person, slot, center_x, center_y, width, height, idle, layout)
        if idle:
            color = ACCENT if len(self.model.contacts) > 1 else '#364258'
            self.avatar.create_text(26, center_y, text='‹', fill=color, font=('Segoe UI', 52))
            self.avatar.create_text(width-26, center_y, text='›', fill=color, font=('Segoe UI', 52))
        self.draw_corner_notification(self.model.notification_total if idle and not self.setup_stage else 0)
        # Keep Tk fonts alive until their replacements exist; deleting every
        # item first makes Tk reload expensive fallback fonts on each frame.
        if previous_items:
            self.avatar.delete(*previous_items)
        if self.model.state == State.RINGING:
            self.ring_geometry = (center_x, center_y, height)
            self.next_ring_frame = 0
            self.animate_ringing(time.monotonic())

    def animate_ringing(self, now):
        """Move existing canvas items; portraits and shaped labels stay alive."""
        if now < getattr(self, 'next_ring_frame', 0) or not getattr(self, 'ring_geometry', None):
            return
        self.next_ring_frame = now + 1/30
        x, y, height = self.ring_geometry
        size = min(240, height-40)
        elapsed = now - self.ringing_started
        for index, offset in enumerate((0, .5)):
            phase = (elapsed/1.8+offset)%1
            maximum = max(8, height/2-8)
            inner = min(size/2+18, maximum*.72)
            radius = inner + (maximum-inner)*phase
            tag = 'ring-pulse-'+str(index)
            self.avatar.coords(tag, x-radius, y-radius, x+radius, y+radius)
            self.avatar.itemconfigure(tag, outline=self.blend_color(BG, GREEN, (1-phase)*.65))
        border = self.blend_color('#31594e', GREEN, .5+.5*math.sin(elapsed*3.5))
        self.avatar.itemconfigure('ring-card', outline=border)

    def draw_card(self, person, slot, center_x, center_y, width, height, idle, layout=None):
        """Draw one interpolated carousel slot; portrait/text references live until the next frame."""
        focus = max(0.0, 1.0-abs(slot))
        selected = focus > .5
        layout = layout or CarouselLayout.fit(width, height, len(self.model.contacts),
                                    (self.model.config or {}).get('carousel_portraits', 3))
        size = min(layout.portrait_size*(.5+.5*focus), max(40, height-132)) if idle else min(152+88*focus, height - (90-50*focus))
        x, y = center_x+(layout.offset(slot) if idle else width*.29*slot), center_y-42 if idle else center_y-12*(1-focus)
        padding = 12+2*focus
        bottom = y+size/2+padding+(44 if idle else 44*(1-focus))+(40 if idle and person else 0)
        ringing = self.model.state == State.RINGING
        current = next((c for c in self.model.contacts if person and c['id'] == person['id']), person)
        available = self.contact_online(current)
        border = self.blend_color('#31594e', GREEN, .5+.5*math.sin((time.monotonic()-(self.ringing_started or 0))*3.5)) if ringing else (GREEN if available else '#66748c') if idle else ACCENT
        self.avatar.create_rectangle(x-size/2-padding, y-size/2-padding, x+size/2+padding, bottom,
                                     fill='#211e32' if selected else PANEL,
                                     outline=border if selected or idle else '#2b3547', width=4 if ringing or idle and selected else 2 if selected else 1,
                                     tags=('ring-card',) if ringing else ())
        image = self.contact_image(person, int(size), '#211e32' if selected else PANEL)
        if image:
            self.current_photos.append(image)
            self.avatar.create_image(x, y, image=image)
        else:
            self.avatar.create_oval(x-size*.4, y-size*.4, x+size*.4, y+size*.4,
                                    fill='#302943' if selected else '#253044', outline='')
            self.avatar.create_text(x, y, text=person['name'].strip()[0].upper() if person else '·',
                                    fill=ACCENT if selected else '#6d7b92', font=(self.font_family, max(10,int(size*.38)), 'bold'))
        if idle and person and person['id'] in self.model.missed_calls:
            self.draw_missed_call(x+size/2-18, y-size/2+18, 22 if selected else 18, person['id'], count=self.model.notification_count(person['id']))
        if idle and self.model.pending_callback(person):
            badge = self.icon_renderer.callback(20 if selected else 16, ACCENT, BG)
            self.current_photos.append(badge)
            self.avatar.create_image(x-size/2+18, y-size/2+18, image=badge,
                                     tags=('callback-pending', 'callback-pending-'+person['id']))
        if idle or focus < .8:
            text = person['name'] if person else '—'
            label_size = 16
            # Keep shaped labels reusable while cards resize. The smallest card
            # determines a width that remains inside every moving card.
            label_width = int(layout.portrait_size*.5+15) if idle else int(size+15)
            color = FG if idle and selected else MUTED
            label = self.text_renderer.photo(text, self.font_family, label_size, '#211e32' if selected else PANEL, color, label_width)
            while label.height() > 44 and label_size > 10:
                label_size -= 1
                label = self.text_renderer.photo(text, self.font_family, label_size, '#211e32' if selected else PANEL, color, label_width)
            shortened = text
            while label.height() > 44 and shortened:
                shortened = shortened[:-1]
                label = self.text_renderer.photo(shortened+'…', self.font_family, label_size,
                                                 '#211e32' if selected else PANEL, color, label_width)
            self.current_text_images.append(label)
            self.avatar.create_image(x, bottom-22-(40 if idle and person else 0), image=label,
                                     tags=('contact-name', 'contact-name-'+person['id']) if person else ())
        if idle and person:
            label_width = min(layout.portrait_size*.5, max(40, height-154)) if self.carousel_motion else size
            self.draw_contact_status(x, bottom, size, padding, selected, available, label_width)
        if ringing:
            phone = self.text_renderer.photo('☎', 'Segoe UI Symbol' if 'Segoe UI Symbol' in self.available_fonts else self.font_family,
                                              28, BG, GREEN, 55)
            self.current_text_images.append(phone)
            self.avatar.create_image(center_x+size/2+62, center_y, image=phone, tags='ring-phone')

    def draw_contact_status(self, x, bottom, size, padding, selected, available, label_width=None):
        color, background = (GREEN, '#193e31') if available else (RED, '#41222a')
        status_y = bottom-20
        self.avatar.create_rectangle(x-size/2-padding+3, bottom-39, x+size/2+padding-3, bottom-3,
                                     fill=background, outline='', tags='contact-online' if available else 'contact-offline')
        self.avatar.create_text(x-size/2+6, status_y, text='✓' if available else '×', fill=color,
                                font=('Segoe UI', 24 if selected else 20, 'bold'))
        font_size = 23 if selected and not self.carousel_motion else 17
        label_width = max(30, int((size if label_width is None else label_width)-20))
        label = self.text_renderer.photo(self.text('online' if available else 'offline'), self.font_family, font_size, background, color, label_width, True)
        while label.height() > 31 and font_size > 10:
            font_size -= 1
            label = self.text_renderer.photo(self.text('online' if available else 'offline'), self.font_family, font_size, background, color, label_width, True)
        self.current_text_images.append(label)
        self.avatar.create_image(x+12, status_y, image=label)

    def draw_corner_notification(self, count):
        if self.corner_notification_state == count:
            return
        self.corner_notification_state = count
        self.hidden_notifications.delete('all')
        if count:
            self.draw_missed_call(32, 28, 22, 'corner', canvas=self.hidden_notifications, count=count)
        else:
            self.hidden_notifications.create_image(24, 28, image=self.corner_logo, tags='zmala-logo')

    def draw_missed_call(self, x, y, radius, contact_id, canvas=None, count=0):
        canvas = self.avatar if canvas is None else canvas
        tags = ('missed-call', 'missed-call-'+contact_id)
        if count:
            tags += ('notification-count',)
        image = self.icon_renderer.missed_call(radius, BADGE_RED, BADGE_WHITE, count=count)
        if canvas is self.avatar:
            self.current_photos.append(image)
        else:
            self.corner_badge_image = image
        canvas.create_image(x, y, image=image, tags=tags)

    @staticmethod
    def blend_color(start, end, amount):
        return '#'+''.join(f'{round(int(start[i:i+2],16)*(1-amount)+int(end[i:i+2],16)*amount):02x}' for i in (1,3,5))

    def contact_image(self, contact, size, background=PANEL):
        if contact and contact.get('photo'):
            file = ROOT / 'data' / contact['photo'].lstrip('/')
            try:
                return self.text_renderer.portrait(file, size, background, fast=bool(self.carousel_motion))
            except (tk.TclError, RuntimeError, OSError, ValueError):
                pass
        return None
