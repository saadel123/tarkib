# Third-party code in Tarkib

Tarkib is MIT licensed (see `../LICENSE`), with one exception:

| File | From | License |
|---|---|---|
| `pipeline/edge_drm.py` | `src/edge_tts/drm.py` of [edge-tts](https://github.com/rany2/edge-tts) 7.3.1, Copyright (C) rany and the edge-tts contributors | GNU Lesser General Public License v3.0 |

`pipeline/edge_drm.py` computes the token that Microsoft Edge's free read-aloud voices need since
13 October 2026. It is a modified copy (the changes are listed at the top of the file), and it is
kept as its own module so you can change or replace it under the terms of the LGPL.

The license texts: `LGPL-3.0.txt` (the GNU Lesser General Public License, version 3) and
`GPL-3.0.txt` (the GNU General Public License, version 3, which the LGPL builds on).
