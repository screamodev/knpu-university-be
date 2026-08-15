# migration/admissions — розділ приймальної комісії

`/uk/division/pryymalna-komisiya` на старому сайті — не сторінка, а розділ зі **150 сторінок**:
поточна кампанія (строки, програми випробувань, розклади, результати, рейтинги, накази про
зарахування, вартість), документація комісії та архіви кампаній 2020–2025. Клієнт попросив
перенести розділ повністю.

| Крок | Скрипт | Що робить |
|---|---|---|
| 1 | `1_crawl.py` | обходить розділ від кореня → `data/pages.json` (slug, назва, група) |
| 2 | `2_emit.py` | переносить тексти через `../pages/migrate_page.py`, перелінковує розділ сам на себе, пише `app/content/admissions/manifest.json` |
| — | `../pass2/mirror_page_files.py` | ~1430 файлів із текстів → Directus, покликання стають `/assets/<uuid>` |

```bash
export DIRECTUS_URL=http://localhost:8055
export DIRECTUS_EMAIL=admin@example.com DIRECTUS_PASSWORD=admin

python3 1_crawl.py --limit 8        # розвідка
python3 1_crawl.py                  # повний обхід
python3 2_emit.py --limit 3         # спробувати
python3 2_emit.py --skip-existing   # перенос усього розділу

cd ../pass2 && python3 mirror_page_files.py --dry-run && python3 mirror_page_files.py
```

Нотатки:

- Межі розділу задає `IN_SECTION` у `1_crawl.py` — без нього краулер піде по всьому старому сайту.
- Групу («campaign» чи «archive-2023») визначає сторінка, з якої вперше прийшли: покликання
  «АРХІВ. Вступна кампанія 2023 року» переводить усе під ним у архів того року.
- Перелінковка в `2_emit.py` замінює `hnpu.edu.ua/uk/<path>` на `/admissions/info/<slug>`, тож
  усередині розділу відвідувач не випадає на старий сайт.
- Фронтенд: `/admissions/committee` (хаб) → `/admissions/info/<slug>` → `/admissions/archive/<рік>`;
  дерево читається з маніфесту в `app/utils/admissionsSection.ts`.
- На прод файли доливає `../pass2/sync_files_map.py` під тими самими uuid — окремо качати не треба.
