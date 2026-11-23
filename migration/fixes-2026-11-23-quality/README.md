# Правки 23.11.2026 — «Якість освіти»: анкети ОП «Хімія та біологія в закладах освіти» (бакалаври) 2026

Документ «Правки 23-27.11.2026», вкладка «Правки 23.11.26», пункт «Навчально-методичний відділ
забезпечення якості освіти» (`/education/quality?tab=quality`). Файли — з Downloads.

| Файл | Куди (`app/content/pages/quality-centre-quality.uk.json`, «Математики, інформатики і природничої освіти», результати) |
| --- | --- |
| `anketa-1-khimiia-biolohiia-bak-osvitnii-protses-2026.pdf` (`2026_Анкета_1_БАК_ОП_Хімія_та_біол_в_закладах_освіти.pdf`) | після «…Хімія та біологія в закладах освіти 2025 рік» |
| `anketa-4-khimiia-biolohiia-bak-robotodavtsi-2026.pdf` (`2026_Анкета_4_БАК_ОП_Хімія_і_біологія_в_ЗО_роботодавці.pdf`) | після «№ 4 ОП Хімія та біологія … 2025 рік» |
| `anketa-5-khimiia-biolohiia-bak-praktyka-2026.pdf` (`2026_Анкета_5_БАК_ОП_Хімія_та_біол_в_ЗО_після_практики.pdf`) | після «№5 ОП Хімія та біологія … 2025 рік» |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-23-quality/push_assets.py --dry-run && DRUN fixes-2026-11-23-quality/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

uuid файла — uuid5 від імені, тож `/assets/<uuid>` у тексті збігається на локалі й на проді.
