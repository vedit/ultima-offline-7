# Original-frame clay studies

The selected first clay pass is `master.png`. The later angular structure and
red colour passes are not sources for these studies. The earlier mouth variants
that stretched the closed clay seam were rejected by the user.

Each new full head was generated separately with the built-in image tool:

| File | Original U7 shape 30 frame | Purpose |
| --- | --- | --- |
| `u7-frame-06.png` | 6 | Small speaking aperture |
| `u7-frame-05.png` | 5 | Medium opening with a raised upper lip |
| `u7-frame-03.png` | 3 | Wide opening with a lowered jaw |

The original pose supplies lip and jaw movement. The selected clay head supplies
camera, character proportions and grey material. Stock UO stone-face art supplies
a secondary projection check. No generated open-mouth frame is used as the
source for another. These are 2D image studies, not renders from a shared 3D mesh.

The mouth openings are transparent. There are no teeth, tongue or trophy mounts.
Source PNGs are preserved unchanged. Review export removes alpha below 16 using
the existing import convention, then applies one fixed crop `(60,40,1010,1390)`
and one preview size `104 x 148`. It does not recenter individual frames or paste
facial regions together. Original retail reference extractions and comparison
previews stay in ignored `game/intro/bin/review/`.

`prompts.json` retains the exact prompts and source roles. `review.json` records
source hashes, transparent opening sizes and differences in nominally fixed
regions. Full-head regeneration still changes some fixed shading and landmarks;
the comparison metrics do not establish pixel-identical geometry. The wide
pose's nose differs more than those in the smaller poses.

This first set is pending visual review. Remaining original mouth poses and
blink combinations are not generated, and the candidates are not installed in
the runtime atlas. The local `clay-original-frames/mouth-study.gif` review loop
uses manual timings to expose transitions; it is not the original lip-sync.
