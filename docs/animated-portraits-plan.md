# Uploaded animated portraits — issue #27

- [x] Create issue and feature branch; retain private portrait experiments.
- [x] Extend validated upload/conversion, immutable serving and backup support to GIF.
- [x] Show format, dimensions, duration and size guidance; validate before upload.
- [x] Play a selected terminal GIF once, hold its last frame and replay on reselection;
      cancel during navigation/calls and bound memory. Static pictures remain supported.
- [x] Keep Android portraits static using a decoded GIF first frame.
- [x] Update Doorstop requirements, traces, direct LLT/HLT plans and assertions.
- [x] Update technical and user-guide sources and regenerate affected derived guides.
- [ ] Raise Android version, run checks, review and create PR; await Verify before merge.
- [ ] Replace private launch hooks with the supported runtime and verify both terminals.

Upload design: all new PNG/JPEG/GIF portraits are square, 480–720 pixels per
side. PNG/JPEG are at most 2 MiB; GIF sources at most 16 MiB, 2–72 frames and
5 seconds (20–2000 ms delays). The server prepares 480 × 480 GIFs with a two-second,
20 fps timeline (40 playback slots), preserving first/last poses; identical adjacent
frames may be combined by GIF encoding. Phone portraits remain static. Historical
static portrait backups remain valid. No personal media is published in the repository.


Local verification: lint and requirements report pass; 173 JavaScript LLT pass
(one platform skip), 47 JavaScript HLT pass (four platform skips), 515 terminal
unit cases pass (11 platform skips), 12 server Python unit cases pass. Both real
Linux HTTP conversion scenarios and the isolated Tk GIF display scenario pass.
Android unit tests and lint pass with the existing Android Studio JDK. All pages
of updated Word sources and regenerated release guides were rendered and inspected.
Hardware qualification/deployment and GitHub Verify remain pending at this stage.
