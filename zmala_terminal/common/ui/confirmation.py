"""Full-screen call and callback confirmation, composed into the terminal display."""
from zmala_terminal.common.model import State
from zmala_terminal.common.theme import BG, FG, RED, PANEL, ACCENT, BUTTON_GREEN, BUTTON_RED


class ConfirmationView:
    # @llr LLR-TERM-UI-010
    def draw_confirmation(self):
        contact = self.model.contact
        if self.model.state not in (State.CONFIRMING, State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK) or not contact:
            return
        width, height = self.root.winfo_width(), self.root.winfo_height()
        key = {State.CONFIRMING:'call_question', State.CONFIRM_CALLBACK:'callback_question', State.REQUESTING_CALLBACK:'wait'}[self.model.state]
        cancelling = bool(self.model.callback_request)
        if cancelling and self.model.state == State.CONFIRM_CALLBACK:
            key = 'cancel'
        self.confirmation_question = self.text(key, name=contact['name'])
        if key == 'cancel':
            self.confirmation_question = self.confirmation_question.capitalize() + ' ?'
        signature = (width, height, contact['id'], contact['name'], contact.get('photo'), self.language, key)
        if signature == self.confirmation_signature:
            return
        self.confirmation_signature = signature
        self.confirmation.delete('all')
        self.confirmation_images = []
        callback = self.model.state in (State.CONFIRM_CALLBACK, State.REQUESTING_CALLBACK)
        choices = self.model.state != State.REQUESTING_CALLBACK
        margin = max(24, min(64, round(height*.045)))
        button_gap = 24
        button_width = min(340, (width-2*margin-button_gap)//2)
        rows = []
        if callback:
            rows.extend([(contact['name'], FG, 24, 'confirmation-name'),
                         (self.text('callback_requested' if cancelling else 'contact_unavailable'),
                          ACCENT if cancelling else RED, 22, 'confirmation-unavailable')])
        rows.append((self.confirmation_question, FG, 32, 'confirmation-question'))
        scale = 1.0
        while True:
            labels = [(self.text_renderer.photo(text, self.font_family, max(16, round(size*scale)),
                                               BG, color, max(100, width-2*margin), True), tag)
                      for text, color, size, tag in rows]
            yes = self.text_renderer.photo(self.text('yes'), self.font_family, max(18, round(28*scale)),
                                           BUTTON_GREEN, FG, max(100, button_width-32), True) if choices else None
            no = self.text_renderer.photo(self.text('no'), self.font_family, max(18, round(28*scale)),
                                          BUTTON_RED, FG, max(100, button_width-32), True) if choices else None
            choice_height = max(64, yes.height()+24, no.height()+24) if choices else 0
            panel_height = margin+16+sum(label.height() for label, _ in labels)+8*(len(labels)-1)
            if choices:
                panel_height += 24+choice_height
            if panel_height <= height*.55 or scale <= .55:
                break
            scale -= .05
        panel_top = height-panel_height
        size = max(1, min(width-2*margin, panel_top-2*margin))
        image = self.contact_image(contact, size, BG)
        if image:
            self.confirmation_images.append(image)
            self.confirmation.create_image(width / 2, panel_top / 2, image=image, tags='confirmed-person')
        else:
            self.confirmation.create_oval(width / 2-size*.3, panel_top / 2-size*.3, width / 2+size*.3, panel_top / 2+size*.3, fill=PANEL, outline='')
            self.confirmation.create_text(width / 2, panel_top / 2, text=contact['name'].strip()[:1].upper(), fill=ACCENT, font=(self.font_family, int(size*.3), 'bold'))
        self.confirmation.create_rectangle(0, panel_top, width, height, fill=BG, outline='')
        y = panel_top+16
        for label, tag in labels:
            self.confirmation_images.append(label)
            self.confirmation.create_image(width / 2, y, image=label, anchor='n', tags=tag)
            y += label.height()+8
        if choices:
            y += 16
            for x, label, color, tag in [(width/2-(button_width+button_gap)/2, yes, BUTTON_GREEN, 'confirmation-yes'),
                                         (width/2+(button_width+button_gap)/2, no, BUTTON_RED, 'confirmation-no')]:
                self.confirmation_images.append(label)
                button = self.icon_renderer.rounded_button(button_width, choice_height, color, BG)
                self.confirmation_images.append(button)
                self.confirmation.create_image(x-button_width/2, y, image=button, anchor='nw',
                                               tags=(tag, tag+'-button'))
                self.confirmation.create_image(x, y+choice_height/2, image=label, tags=tag)
