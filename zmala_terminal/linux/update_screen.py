"""Independent localized HDMI progress; never controls TV, USB, media or calls."""
import io
import json
from pathlib import Path

# @llr LLR-TERM-UI-028
MESSAGES = {
 'en': ('Updating ZmalaCall. Please wait.', 'Checking the update. Please wait.', 'Restoring ZmalaCall. Please wait.', 'ZmalaCall needs help. Please contact the person who set it up.'),
 'fr': ('Mise à jour de ZmalaCall. Veuillez patienter.', 'Vérification de la mise à jour. Veuillez patienter.', 'Restauration de ZmalaCall. Veuillez patienter.', 'ZmalaCall a besoin d’aide. Contactez la personne qui l’a installé.'),
 'de': ('ZmalaCall wird aktualisiert. Bitte warten.', 'Das Update wird geprüft. Bitte warten.', 'ZmalaCall wird wiederhergestellt. Bitte warten.', 'ZmalaCall benötigt Hilfe. Bitte kontaktieren Sie die Person, die es eingerichtet hat.'),
 'es': ('Actualizando ZmalaCall. Espere, por favor.', 'Comprobando la actualización. Espere, por favor.', 'Restaurando ZmalaCall. Espere, por favor.', 'ZmalaCall necesita ayuda. Contacte con la persona que lo configuró.'),
 'pt': ('A atualizar o ZmalaCall. Aguarde, por favor.', 'A verificar a atualização. Aguarde, por favor.', 'A restaurar o ZmalaCall. Aguarde, por favor.', 'O ZmalaCall precisa de ajuda. Contacte quem o configurou.'),
 'pl': ('Aktualizowanie ZmalaCall. Proszę czekać.', 'Sprawdzanie aktualizacji. Proszę czekać.', 'Przywracanie ZmalaCall. Proszę czekać.', 'ZmalaCall potrzebuje pomocy. Skontaktuj się z osobą, która go skonfigurowała.'),
 'el': ('Ενημέρωση του ZmalaCall. Παρακαλώ περιμένετε.', 'Έλεγχος ενημέρωσης. Παρακαλώ περιμένετε.', 'Επαναφορά του ZmalaCall. Παρακαλώ περιμένετε.', 'Το ZmalaCall χρειάζεται βοήθεια. Επικοινωνήστε με το άτομο που το εγκατέστησε.'),
 'ru': ('Обновление ZmalaCall. Пожалуйста, подождите.', 'Проверка обновления. Пожалуйста, подождите.', 'Восстановление ZmalaCall. Пожалуйста, подождите.', 'ZmalaCall нужна помощь. Обратитесь к тому, кто его настроил.'),
 'ur': ('ZmalaCall کو اپ ڈیٹ کیا جا رہا ہے۔ براہ کرم انتظار کریں۔', 'اپ ڈیٹ کی جانچ ہو رہی ہے۔ براہ کرم انتظار کریں۔', 'ZmalaCall بحال کیا جا رہا ہے۔ براہ کرم انتظار کریں۔', 'ZmalaCall کو مدد کی ضرورت ہے۔ اسے ترتیب دینے والے شخص سے رابطہ کریں۔'),
 'ar': ('جارٍ تحديث ZmalaCall. يُرجى الانتظار.', 'جارٍ التحقق من التحديث. يُرجى الانتظار.', 'جارٍ استعادة ZmalaCall. يُرجى الانتظار.', 'يحتاج ZmalaCall إلى مساعدة. يُرجى التواصل مع الشخص الذي أعدّه.'),
 'hi': ('ZmalaCall अपडेट हो रहा है। कृपया प्रतीक्षा करें।', 'अपडेट की जाँच हो रही है। कृपया प्रतीक्षा करें।', 'ZmalaCall बहाल हो रहा है। कृपया प्रतीक्षा करें।', 'ZmalaCall को सहायता चाहिए। इसे सेट अप करने वाले व्यक्ति से संपर्क करें।'),
 'bn': ('ZmalaCall আপডেট হচ্ছে। অনুগ্রহ করে অপেক্ষা করুন।', 'আপডেট যাচাই হচ্ছে। অনুগ্রহ করে অপেক্ষা করুন।', 'ZmalaCall পুনরুদ্ধার হচ্ছে। অনুগ্রহ করে অপেক্ষা করুন।', 'ZmalaCall-এর সহায়তা প্রয়োজন। যিনি এটি সেট আপ করেছেন তাঁর সঙ্গে যোগাযোগ করুন।'),
 'th': ('กำลังอัปเดต ZmalaCall โปรดรอสักครู่', 'กำลังตรวจสอบการอัปเดต โปรดรอสักครู่', 'กำลังกู้คืน ZmalaCall โปรดรอสักครู่', 'ZmalaCall ต้องการความช่วยเหลือ โปรดติดต่อผู้ที่ตั้งค่าระบบให้คุณ'),
 'ko': ('ZmalaCall 업데이트 중입니다. 잠시 기다려 주세요.', '업데이트를 확인 중입니다. 잠시 기다려 주세요.', 'ZmalaCall 복원 중입니다. 잠시 기다려 주세요.', 'ZmalaCall에 도움이 필요합니다. 설정해 준 분에게 문의해 주세요.'),
 'ja': ('ZmalaCall を更新しています。しばらくお待ちください。', '更新を確認しています。しばらくお待ちください。', 'ZmalaCall を復元しています。しばらくお待ちください。', 'ZmalaCall にサポートが必要です。設定した方にご連絡ください。'),
 'zh-Hans': ('正在更新 ZmalaCall，请稍候。', '正在检查更新，请稍候。', '正在恢复 ZmalaCall，请稍候。', 'ZmalaCall 需要帮助。请联系为您设置设备的人。'),
}
STATES = {'updating': 0, 'checking': 1, 'rollback': 2, 'recovery_failed': 3}


def message(language, phase):
    return MESSAGES.get(language, MESSAGES['en'])[STATES[phase]]


def render_message(text, language, width, height):
    # Kept independent of the application renderer: this process must survive
    # replacement of every application module while retaining Pango bidi shaping.
    import cairo
    import gi
    gi.require_version('Pango', '1.0')
    gi.require_version('PangoCairo', '1.0')
    from gi.repository import Pango, PangoCairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(13/255, 18/255, 28/255)
    context.paint()
    layout = PangoCairo.create_layout(context)
    layout.get_context().set_language(Pango.Language.from_string(language))
    layout.set_text(text, -1)
    layout.set_width(int(width * .8) * Pango.SCALE)
    layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    layout.set_alignment(Pango.Alignment.CENTER)
    for size in range(min(52, max(26, width//24)), 19, -1):
        font = Pango.FontDescription('Noto Sans')
        font.set_size(size * Pango.SCALE)
        layout.set_font_description(font)
        measured_width, measured_height = layout.get_pixel_size()
        if measured_height <= height * .65:
            break
    context.set_source_rgb(237/255, 241/255, 251/255)
    context.move_to((width - measured_width)/2, (height-measured_height)/2)
    PangoCairo.show_layout(context, layout)
    stream = io.BytesIO()
    surface.write_to_png(stream)
    return stream.getvalue(), (measured_width, measured_height)


# @llr LLR-TERM-UI-028
def main(state_file='/run/zmalacall-updater/state.json'):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.title("ZmalaCall update")
    root.overrideredirect(True)
    root.configure(bg='#0d121c')
    width, height = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f'{width}x{height}+0+0')
    canvas = tk.Canvas(root, bg='#0d121c', highlightthickness=0)
    canvas.pack(fill='both', expand=True)
    previous = None
    def refresh():
        nonlocal previous
        try:
            path = Path(state_file)
            if path.stat().st_size > 8192:
                raise ValueError('Invalid state')
            value = json.loads(path.read_text(encoding='utf-8'))
            phase, language = value.get('phase'), value.get('language', 'en')
            if phase not in STATES:
                root.withdraw()
                previous = None
            else:
                if (phase, language) != previous:
                    data, _ = render_message(message(language, phase), language, width, height)
                    root.image = tk.PhotoImage(master=root, data=data, format='PNG')
                    canvas.delete('all')
                    canvas.create_image(width//2, height//2, image=root.image)
                    previous = phase, language
                root.deiconify()
                root.lift()
        except (OSError, ValueError, TypeError, KeyError):
            # Retain an already displayed recovery message if the producer dies.
            pass
        root.after(500, refresh)
    refresh()
    root.mainloop()


if __name__ == '__main__':
    main()
