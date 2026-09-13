# Правки 13.09.2026

П'ятий набір правок: PDF «правки 13.09.2026» (кафедри соціально-гуманітарного факультету,
Студентський Парламент, кафедра практики англійського мовлення).

## Що куди їде

| Що | Куди |
| --- | --- |
| нові поля `emblem`, `photo`, `legalBasis` у `student_council_info` | схема |
| емблема й загальне фото парламенту | медіатека; `student_council_info.emblem` / `.photo` |
| тексти «Про самоврядування», мета, завдання, нормативна база | `student_council_info` (`set_council_info.py`) |
| категорія галереї «Студентський парламент» | `gallery_categories`, slug `student-parliament` |
| 5 фото Форуму лідерів ОСС | `gallery_items`; файли студенти вже залили на прод 12.09 оригіналами |
| 6 фото квартирника «Коли серце говорить вголос» | медіатека + `gallery_items` |

Кафедри соцгуму й кафедра англійського мовлення — лише статичний контент фронту.

## Як накотити

```bash
cd migration
python3 schema/apply_schema.py --dry-run     # 3 поля student_council_info + 2 relations
python3 schema/apply_schema.py

python3 fixes-2026-09-13/push_assets.py --dry-run   # 8 файлів
python3 fixes-2026-09-13/push_assets.py

python3 pass2/load.py fixes-2026-09-13/data/fixes-2026-09-13.json --dry-run
python3 pass2/load.py fixes-2026-09-13/data/fixes-2026-09-13.json

python3 fixes-2026-09-13/set_council_info.py --dry-run
python3 fixes-2026-09-13/set_council_info.py
```

`set_council_info.py` заповнює лише порожні поля — те, що студенти вже вписали в адмінці,
лишається (`--force` перезаписує).

Фото Форуму посилаються на файли, які існують лише на проді (`Форум ОСС*.JPG`). На локалі ці 5
рядків `gallery_items` не створяться — це очікувано.

Файли вийняті з PDF правок, тож якість — як у PDF (близько 1000 px). Оригіналів квартирника
й групового фото клієнт не надсилав.
