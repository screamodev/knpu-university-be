# Правки 08.09.2026

Другий набір правок за документом клієнта «2026_09_07_Правки» — пункти, дописані після нашого
UPD від 07.09.

## Що куди їде

| Що | Куди |
| --- | --- |
| 12 угод про проведення практик і 4 договори про творчу співпрацю (PDF, кафедра спеціальної педагогіки) | файли в медіатеку; посилання вже стоять у `app/content/structure/kafedra-specialnoyi-pedagogiky/cooperation.uk.json` |
| 3 звіти Студентського Парламенту (PDF) | `documents`, новий розділ `student-council-reports` — блок «Звіти Студентського Парламенту» на `/student/council` |
| 4 плани заходів Центру інклюзивної освіти (DOC) | `documents`, розділ `inclusive-support` — `/university/inclusive` |
| рубрика «Навчально-методичний інклюзивний центр» | `categories` |
| 2 анонси конференцій (15.10.2026 і 29.10.2026) | `science_conferences` — `/science/conferences` |
| підзаголовки «Денна форма» / «Заочна форма» / «Накази» | поле `documents.group` рядків розділу `education-schedule` |

## Як накотити

```bash
cd migration
export DIRECTUS_URL=http://knpu-university-directus:8055
export DIRECTUS_TOKEN=…

# 1. Поле documents.group і новий розділ documents.section
python3 schema/apply_schema.py --dry-run     # + field documents.group, documents.groupEn,
python3 schema/apply_schema.py               #   + documents.section: student-council-reports

# 2. Файли (публічні качає з Drive сам, плани лежать у files/ в git)
python3 fixes-2026-09-08/push_assets.py --dry-run   # 21 файл
python3 fixes-2026-09-08/push_assets.py

# 3. Рядки
python3 pass2/load.py fixes-2026-09-08/data/fixes-2026-09-08.json --dry-run
python3 pass2/load.py fixes-2026-09-08/data/fixes-2026-09-08.json

# 4. Підзаголовки графіка освітнього процесу
python3 fixes-2026-09-08/set_schedule_groups.py --dry-run
python3 fixes-2026-09-08/set_schedule_groups.py
```

Після зміни схеми — `snapshots/bootstrap-public-access.sh` і `bootstrap-editor-role.sh`, як завжди.

Усі чотири кроки ідемпотентні.

## Чого тут немає і чому

* **План заходів Центру інклюзивної освіти у 2022–2023 н. р.** — у теці на Drive лежить під
  латинською назвою (`Plan zahogiv Tsentru…`) і не завантажився разом з рештою. Решта чотирьох
  років на місці; цей чекаємо окремим файлом.
* **Угода з Волинським НУ за 2025 р.** — клієнт просив додати рядок «2025» під 2022 і 2023,
  але покликання на саму угоду не надіслав.
* **Новини кафедри спеціальної педагогіки за 2022 — березень 2025** і **23 новини
  Навчально-методичного інклюзивного центру** — під час міграції зі старого сайту не
  перенеслися, у базі їх немає. Кафедра надіслала повний архів (~120 новин з теками фото на
  Drive) — це окремий обсяг робіт, не цей пакет. Рубрику центру створюємо порожньою, щоб
  редактор міг ставити тег.
