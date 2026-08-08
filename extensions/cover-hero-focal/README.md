# Cover hero focal (`cover-hero-focal`)

Directus interface for article covers: drag a hero-aspect rectangle on the image, see a live FE-style preview, and save `focal_point_x` / `focal_point_y` on the file immediately (no article Save required).

## Develop

```bash
cd extensions/cover-hero-focal
npm install
npm run build
```

Restart Directus so it picks up the extension (`docker compose restart directus` from `knpu-university-be`).

## Enable on a field

Settings → Data Model → Articles → `cover` → Interface: **Cover + hero frame**  
(or apply the schema snapshot). Option: `aspectRatio` (default `2.5` = 5/2, same as the public article hero).
