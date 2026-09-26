# Правки 25.09.2026 (п. 19, 20) — Центр ментального здоров'я і Валеоклуб

Матеріали — docx «Коригування сайту ХНПУ» з пошти.

| Що | Куди |
| --- | --- |
| `valeoklub-1.jpg`, `valeoklub-2.jpg` | медіатека; вкладка «Валеоклуб» центру ментального здоров'я і кафедри корекційної психопедагогіки |
| категорія новин «Валеоклуб» (дочірня до `mental-health-centre`) | `categories` (`data/fixes-2026-09-25-mental.json`) |

```bash
cd migration
python3 fixes-2026-09-25-mental/push_assets.py --dry-run   # 2 файли
python3 fixes-2026-09-25-mental/push_assets.py
python3 pass2/load.py fixes-2026-09-25-mental/data/fixes-2026-09-25-mental.json
```
