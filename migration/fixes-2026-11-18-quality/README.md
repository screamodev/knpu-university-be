# Правки 18.11.2026 — «Якість освіти»: анкети ОП «Право» (магістри) 2026

Документ «Правки 16-20.11.2026», вкладка «Правки 18.11.26», пункт «Навчально-методичний відділ
забезпечення якості освіти» (`/education/quality?tab=quality`). Файли — з Downloads.

| Файл | Куди (`app/content/pages/quality-centre-quality.uk.json`, «Історії і права») |
| --- | --- |
| `anketa-pravo-mag-osvitnii-protses-2026.pdf` (`2026_Анкета 1_Право_МАГ.pdf`) | у першому списку, останнім — після «…Історія в закладах освіти 2023 рік» |
| `anketa-4-pravo-mag-robotodavtsi-2026.pdf` (`2026_Анкета_4_Право_МАГ_співпраця_з_роботодавцями.pdf`) | у списку анкет № 4, останнім — після «№ 4 «Оцінювання співпраці з роботодавцями» 2024 рік» |

```bash
cd /root/knpu-university-be && git pull
cd migration
set -a; . /root/knpu-university-be/.env; set +a
DRUN() { docker run --rm --network webnet \
  -e DIRECTUS_URL=http://knpu-university-directus:8055 \
  -e DIRECTUS_EMAIL="$ADMIN_EMAIL" -e DIRECTUS_PASSWORD="$ADMIN_PASSWORD" \
  -e DIRECTUS_TOKEN= \
  -v /root/knpu-university-be/migration:/m -w /m python:3.12-slim python3 "$@"; }
DRUN fixes-2026-11-18-quality/push_assets.py --dry-run && DRUN fixes-2026-11-18-quality/push_assets.py
cd /root/knpu-university-fe && git pull
docker compose -f docker-compose.prod.yml up -d --build
docker ps --filter name=knpu-university-fe --format "{{.Status}}"   # Up N seconds
```

uuid файла — uuid5 від імені, тож `/assets/<uuid>` у тексті збігається на локалі й на проді.
