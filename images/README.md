# Images — Mansão do Lago

Web-optimized photos for the static site. **Originals stay untouched** in `assets/photos/` when available.

## Specs (after 2026-07 overhaul)

| Setting | Value |
|--------|--------|
| Max side | 1920 px |
| Format | JPEG (q82, progressive) / PNG for floorplans |
| EXIF | stripped on re-export |
| Naming | `mansao-do-lago-{description}-01.jpg` |

## Folder structure

| Folder | Use on site | Notes |
|--------|-------------|--------|
| `hero/` | Home / page heroes | Best hero: `hero-piscina-fachada-01` |
| `entrance/` | Chegada / home videos | New entrance stills |
| `lake/` | Lago, ponte | Guest leisure + brand |
| `lakegarden/` | Jardim junto ao lago | New garden-lake set |
| `garden/` | Jardins | Guest leisure |
| `pool/` | Piscina, cascata, jacuzzi | Guest leisure |
| `night/` | Noite | Atmosphere |
| `pub/` | Pub inglês, adega | Guest leisure |
| `gourmet/` | Área gourmet | Guest / events |
| `varandas/` | Varandas e decks | Guest leisure |
| `gym-sauna/` | Academia, sauna | Guest leisure |
| `suite/` | **Only** guest suite | Airbnb/Booking inventory |
| `kitchen/` | Cozinha (ilha, gourmet) | Events / filmings interiors |
| `interiors/` | Salas, halls, jantar | Events + filmings |
| `master-suites/` | Suítes da família | Filmings only (not guest rental) |
| `suportrooms/` | Quartos de apoio / vistas | Filmings / atmosphere |
| `office/` | Escritório | Filmings / meetings |
| `exterior/` | Fachada, portão, garagem | Context |
| `events/` | Festas e celebrações | Events page |
| `filmings/` | Produções com equipe | Filmagens page |
| `floorplan/` | Planta lazer | Reference |
| `hosts/` | Cintia | `cintia-host.jpg` is primary |
| `surroundings/` | Entorno / landmarks | `entorno.html` only |
| `logos/` | Airbnb, Booking, Spotz | UI only |

## Guest vs filmings/events

- **Guest stay:** suite + leisure (lake, lakegarden, garden, pool, pub, gourmet, varandas, gym-sauna, entrance).
- **Filmings / events:** also interiors, kitchen, office, master-suites, suportrooms, full house.
- Production with crew → `filmings/`. Birthday/party → `events/`.

## House videos

Short ambient MP4s of rooms/grounds: `videos/home/`. Wired on the home page via `js/site-media.js` → `home.videos`.

## Update workflow

1. Drop files into the right folder under `images/` (or `videos/home/`).
2. Run `python scripts/overhaul_media.py` if files are large / phone dumps.
3. Run `python scripts/rebuild_gallery_and_media.py` to refresh gallery + catalog (or edit `js/site-media.js` by hand).
4. Check pages and `galeria.html`.
