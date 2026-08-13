# Videos — Mansão do Lago

## Structure

```
videos/
  home/         → short ambient clips of the house (rooms & grounds)
  events/       → event aftermovies (optional, empty for now)
  filmings/     → production showreels (optional; YouTube is used on filmagens page)
```

## Home house clips (`videos/home/`)

These are **not** events or filmings — they show the property itself:

| File | Suggested subject |
|------|-------------------|
| `arrival.mp4` | Entrance / arrival |
| `bridge.mp4` | Lake bridge |
| `fishes.mp4` | Lake life |
| `lakegarden.mp4` | Garden by the lake |
| `lakegarde2.mp4` | Garden (second angle) |
| `pub1.mp4` / `pub2.mp4` | English pub |
| `gym.mp4` | Gym |

Wired on the **home page** via `js/site-media.js` → `home.videos` (HTML: `data-media-video-list="home.videos"`).

Videos use `preload="none"` so they only download when the guest presses play.

## Tips for web weight

Each clip is currently ~17–30 MB. For faster mobile loads later, re-export as H.264 720p or 1080p, CRF ~28, and shorter duration when possible.
