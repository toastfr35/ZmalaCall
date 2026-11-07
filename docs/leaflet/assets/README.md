# Leaflet graphics

Hardware and overview graphic files are text-free. Captions, component names,
step numbers and instructions belong to the HTML/locale layer. Do not bake
translated labels into images. Keep the physical connector diagram in its
original left-to-right order. The cover uses the approved official Zmala wordmark
from `docs/branding/PNG/a1-wordmark-light-1024.png` directly, without redrawing or
duplicating it. This brand asset is the intentional exception to text-free art.

- `overview.png`: text-free derivative of `docs/images/zmala-overview.png`, the
  README illustration. Created with the built-in image-generation tool. The
  original illustration is retained unchanged.
- `case.svg`: authored, text-free drawing of the sloped enclosure, rear lid,
  side vents and dark base, checked against the manufacturer's
  [Argon ONE V2 product photographs](https://argon40.com/products/argon-one-v2-case-for-raspberry-pi-4).
  The front is shown without connectors; the rear connector view is separate.
- `ports.svg`: schematic based on the Argon ONE Pi 4 V2 connection drawing
  retained in `docs/terminal_prep.docx`. Not to scale.
- `c10.svg`: authored schematic illustration, checked against the manufacturer's
  [C10 product page](https://nuroum.com/uk/product/all-in-one-webcam-c10).
- `remote.svg` and `remote-back.svg`: authored schematics based on the front/back
  pairing illustration in `docs/terminal_config.docx`. The green/red button
  stickers are preserved. The rear Bluetooth button is highlighted.
- `buttons-arrows.svg`, `button-middle.svg`, `button-green.svg` and
  `button-red.svg`: enlarged button details. The arrow pair uses two circular
  buttons with white chevrons; the long middle button has the white pointer
  symbol shown on the retained remote illustration. The button positions and
  shapes were also checked against the
  [manufacturer's remote guide](https://support.microsoft.com/en-us/surface/accessories/certified/set-up-and-use-microsoft-presenter).

The final built-in image edit prompt was:

> Edit target: the provided Zmala README overview illustration. Create a faithful
> text-free edition for a multilingual printed leaflet. Preserve the people,
> television, phone, cameras, servers, arrows, composition, illustration style,
> colours, and wide aspect ratio. Remove all three purple label pills AND their
> text ('Zmala Server', 'Zmala Terminal', 'Zmala Phone'), naturally continuing the
> cream background in those areas. No letters, words, numbers, captions or
> watermarks anywhere. Preserve icon-only call controls. Save the resulting image.
