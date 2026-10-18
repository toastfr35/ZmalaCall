from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'tmp/pdfs/ZmalaCall-Pi4-Installation-Guide.pdf'
OUT.parent.mkdir(parents=True, exist_ok=True)
for name, fn in [('Segoe','segoeui.ttf'), ('SegoeBold','segoeuib.ttf')]:
    pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/'+fn))
pdfmetrics.registerFontFamily('Segoe',normal='Segoe',bold='SegoeBold')
W,H=A4
NAVY=colors.HexColor('#13263c'); INK=colors.HexColor('#23364b'); BLUE=colors.HexColor('#1475bb'); MUTED=colors.HexColor('#5a6c7c'); PALE=colors.HexColor('#eef4f8')
c=canvas.Canvas(str(OUT),pagesize=A4)
c.setTitle('ZmalaCall | Raspberry Pi 4 installation guide')
c.setAuthor('ZmalaCall')
def p(txt,x,y,width=507,size=11,leading=16,color=INK):
    s=ParagraphStyle('p',fontName='Segoe',fontSize=size,leading=leading,textColor=color)
    q=Paragraph(txt,s); _,h=q.wrap(width,900); q.drawOn(c,x,H-y-h); return y+h
def text(txt,x,y,size=11,bold=False,color=INK):
    c.setFillColor(color);c.setFont('SegoeBold' if bold else 'Segoe',size);c.drawString(x,H-y,txt)
def box(x,y,w,h,fill=PALE,r=10):
    c.setFillColor(fill);c.roundRect(x,H-y-h,w,h,r,stroke=0,fill=1)
def img(file,x,y,w):
    im=Image.open(file);h=w*im.height/im.width;c.drawImage(str(file),x,H-y-h,w,h,mask='auto');return y+h
def start(n,title,subtitle):
    c.setFillColor(NAVY);c.rect(0,H-9,W,9,stroke=0,fill=1)
    img(ROOT/'zmala_terminal/common/assets/zmala-icon.png',44,28,28)
    text('ZMALACALL  /  FRESH SD CARD',84,47,10,True,BLUE)
    text(title,44,96,25,True,NAVY)
    p(subtitle,44,111,size=11,color=MUTED)
    c.setStrokeColor(colors.HexColor('#dce4ea'));c.line(44,46,W-44,46)
    text('Raspberry Pi 4 · Argon ONE Pi 4 V2 · 17 October 2026',44,H-29,8,color=MUTED)
    text(f'{n} / 4',W-67,H-29,8,color=MUTED)
def heading(txt,y):text(txt,44,y,14,True,NAVY)
def link(label,url,y):return p(f'<link href="{url}" color="#1475bb"><u>{label}</u></link>',44,y,size=10,leading=14)

start(1,'1. Prepare the SD card','Use a Windows PC and an SD card reader. No keyboard or mouse is needed on the Pi.')
heading('Get the software',166)
y=link('Download Raspberry Pi Imager - official website','https://www.raspberrypi.com/software/',180)
y=p('Install the current Imager release. Select the OS from its catalogue so the correct customisation options are available.',44,y+8)
y=link('Download Zmala terminal setup from GitHub Actions', 'https://github.com/toastfr35/ZmalaCall/actions/workflows/build-terminal-installer.yml',y+10)
p('Sign in to GitHub. Open the latest successful main build, download the<br/><b>zmala-terminal-setup</b> artifact and extract the ZIP. Run <b>zmala_terminal_setup.exe</b>.',44,y+5,size=9,leading=13,color=MUTED)
heading('Choose the device, OS and storage',314)
p('<b>Device:</b> Raspberry Pi 4<br/><b>OS:</b> Raspberry Pi OS Lite (64-bit), Debian 13 Trixie<br/><b>Storage:</b> the microSD card you intend to erase',44,330)
heading('Set these options before writing',403)
rows=[['Setting','Value'],['Hostname','zmala'],['Username','zmala'],['Password','zmala'],['SSH / remote access','Enabled, password authentication'],['Wi-Fi','Leave credentials unset; configure by QR later'],['Localisation','Your country, time zone and keyboard layout']]
tbl=Table(rows,colWidths=[146,361],rowHeights=[29]*7)
tbl.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'Segoe'),('FONTNAME',(0,0),(-1,0),'SegoeBold'),('FONTSIZE',(0,0),(-1,-1),10),('BACKGROUND',(0,0),(-1,0),NAVY),('TEXTCOLOR',(0,0),(-1,0),colors.white),('TEXTCOLOR',(0,1),(-1,-1),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[PALE,colors.white]),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),12)]))
tbl.wrap(507,300);tbl.drawOn(c,44,H-421-203)
p('Choose the correct Wi-Fi country if Imager offers that field. Screen labels can vary between Imager versions.',44,634,size=9,leading=13,color=MUTED)
box(44,674,507,72)
p('<b>Writing erases the selected card.</b><br/>Double-check the drive, write the image and let verification finish. Safely eject the card, then insert it into the powered-off Pi.',58,687,479)
link('Official Imager and first-boot instructions','https://www.raspberrypi.com/documentation/computers/getting-started.html',762)
c.showPage()

start(2,'2. Connect the equipment','Argon ONE Pi 4 V2 case - rear view. Connect power last.')
# Schematic is vector artwork, with physical port order checked against the case manual.
box(44,163,507,363,colors.HexColor('#f3f6fa'))
def device(x,y,w,title,sub,col):
    box(x,y,w,61,colors.white,7)
    c.setStrokeColor(col);c.setLineWidth(2);c.line(x+10,H-y-8,x+w-10,H-y-8)
    text(title,x+10,y+29,11,True,col);p(sub,x+10,y+36,w-20,8,11,MUTED)
purple=colors.HexColor('#7651ba');green=colors.HexColor('#16886e');orange=colors.HexColor('#c77b15')
device(58,179,135,'TV / HDMI','Full-size HDMI cable',purple)
device(216,179,135,'Remote charger','USB cable from cradle',green)
device(374,179,163,'Nuroum C20','Camera USB cable',BLUE)
device(61,442,184,'USB-C power supply','Suitable for Pi 4: 5 V, at least 3 A',orange)
device(346,442,188,'Router / network','Ethernet with Internet access',MUTED)
box(62,305,472,109,colors.HexColor('#34414d'),7)
text('USB-C POWER',151,333,7,True,colors.white)
def port(x,y,w,h,col=colors.HexColor('#101820')):
    c.setFillColor(col);c.setStrokeColor(colors.HexColor('#bdc9d3'));c.setLineWidth(1);c.roundRect(x,H-y-h,w,h,3,stroke=1,fill=1)
port(80,341,22,49);port(111,341,22,49)
port(159,343,39,14)
c.setFillColor(colors.HexColor('#101820'));c.circle(179,H-380,10,fill=1,stroke=0)
for py in [341,372]:port(248,py,54,22)
for py in [341,372]:port(343,py,54,22,BLUE)
port(455,360,58,36);port(462,336,44,13)
text('HDMI',82,404,8,color=colors.white);text('Audio (unused)',150,404,7,color=colors.white)
text('USB 2',251,404,8,color=colors.white);text('USB 3',346,404,8,color=colors.white);text('LAN',468,408,8,color=colors.white)
text('POWER',468,345,6,color=colors.white)
def wire(points,col):
    c.setStrokeColor(col);c.setLineWidth(3)
    path=c.beginPath();path.moveTo(points[0][0],H-points[0][1])
    for xx,yy in points[1:]:path.lineTo(xx,H-yy)
    c.drawPath(path)
    xx,yy=points[-1];c.setFillColor(col);c.circle(xx,H-yy,4,stroke=0,fill=1)
wire([(123,240),(123,274),(91,274),(91,355)],purple)
wire([(283,240),(283,276),(275,276),(275,352)],green)
wire([(455,240),(455,286),(370,286),(370,352)],BLUE)
wire([(153,442),(153,424),(219,424),(219,350),(179,350)],orange)
wire([(441,442),(441,426),(484,426),(484,378)],MUTED)
p('Connection diagram, not to scale. Port layout follows the Argon ONE Pi 4 V2 manual.',58,511,479,8,11,MUTED)
heading('Before you switch on',558)
y=p('<b>Camera:</b> connect the C20 to a blue USB 3 socket.<br/><b>Charger:</b> connect the Presenter cradle to the adjacent black USB socket.<br/><b>TV:</b> connect one full-size HDMI socket on the case to the TV, then select that TV input. The second HDMI socket is unused.<br/><b>Network:</b> keep Ethernet connected throughout installation. The Windows PC must be able to reach the Pi on the same local network.',44,571)
box(44,685,507,65)
p('<b>Now connect USB-C power.</b> If the Pi does not start, press the case power button once. Allow the first boot to finish before checking it from Windows.',58,698,479)
c.showPage()

start(3,'3. Install ZmalaCall','The Windows installer performs the transfer, installation, reboot and startup checks.')
heading('Open zmala_terminal_setup.exe',169)
p('No separate Python, SSH client or manual Pi commands are required. Keep the Pi powered and Ethernet connected until installation completes.',44,182)
# Clear, labelled UI guide rather than an invented screenshot.
box(44,234,507,161,NAVY)
text('INSTALLER CONTROLS',61,259,9,True,colors.HexColor('#93bbdc'))
text('Pi hostname / Ethernet IP',61,287,10,color=colors.white)
box(256,269,274,27,colors.white,4);text('zmala.local',268,287,11)
text('Argon ONE Pi 4 V2 fan setup is included automatically',61,320,11,color=colors.white)
for x,w,label in [(61,136,'1. Check Pi'),(210,136,'2. Install...'),(407,123,'View details')]:
    box(x,341,w,34,colors.HexColor('#e5eff7'),5);text(label,x+13,363,11,True)
p('Control guide; the actual Windows window may look slightly different.',44,404,size=9,leading=13,color=MUTED)
heading('Check, confirm, wait',450)
y=p('<b>1. Check Pi.</b> The hostname is <b>zmala</b>; its network address is <b>zmala.local</b>. If it cannot be found, use its Ethernet IP from your router. The installer checks the connection, Pi model, OS and storage.',44,465)
y=p('<b>2. Install.</b> Argon ONE fan setup is automatic. Confirm the target in the dialog, then wait for the automatic reboot and final success message.',44,y+12)
y=p('<b>3. Continue on the TV.</b> The Zmala boot image and first-start instructions should appear. A short blank screen during boot or HDMI negotiation can be normal.',44,y+12)
heading('Already handled by the installer',637)
p('Automatic startup and boot branding; Argon fan control during connected calls; SSH restricted to Ethernet; reduced SD writes using RAM logs, RAM-only swap and temporary runtime files.',44,650)
box(44,706,507,57)
p('<b>If an error appears:</b> keep power and Ethernet connected. Choose <b>View details</b>, then <b>Open saved log</b>. A lost connection may not stop installation on the Pi.',58,718,479,size=10,leading=14)
c.showPage()

start(4,'4. Finish setup on the TV','Have the Wi-Fi QR code and the terminal\'s server QR code ready. Keep the server running.')
heading('Pair the Microsoft Presenter+ remote',168)
p('Switch the remote on. Turn it over and hold the rear Bluetooth button for about <b>3 seconds</b>, until the white light flashes. Pairing happens automatically.',44,182)
img(ROOT/'zmala_terminal/common/assets/presenter-pairing.png',93,237,410)
p('Front at left; back at right. After pairing, press and release Left, Right, Green, Red and Middle as prompted. QR setup starts only after all five buttons pass the test.',44,475,size=9,leading=13,color=MUTED)
heading('Scan the two QR codes',516)
y=p('<b>1. Wi-Fi QR:</b> hold it in front of the C20 and wait for the connection to succeed.<br/><b>2. Server QR:</b> scan it next to enroll the terminal. Its ID comes from this QR, not from the Pi hostname or the installer.',44,530)
box(44,593,507,63)
p('<b>Replacing term2:</b> keep the old terminal stopped. Reuse its existing server QR if its address and credentials are still valid. Never run both terminals with the same identity.',58,605,479,size=10,leading=14)
heading('Final check',686)
p('Confirm that contacts appear and the remote buttons work. Make a test call and check picture and sound in both directions. Setup screens are in English; enrollment applies the selected language.',44,699,size=10,leading=14)
p('If setup stalls: check the C20 cable, charge the remote, or check the scanned QR. The USB help screen appears automatically when the C20 is missing.',44,749,size=9,leading=12,color=MUTED)
c.save()
print(OUT)
