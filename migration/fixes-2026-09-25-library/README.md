# Правки 25.09.2026 (п. 1) — Наукова бібліотека

Матеріали — docx «Зміни у кнопках Наукової бібліотеки на Сайт», «Історія бібліотеки» і три
зображення з пошти.

| Що | Куди |
| --- | --- |
| `library-structure.jpg`, `library-services.jpg`, `library-projects.jpg` | медіатека; розділи «Про бібліотеку», «Послуги», «Проєкти» сторінки `/science/library` (`app/content/pages/science-library.uk.json`) |

Положення про наукову бібліотеку вже є в медіатеці (розділ документів «Нормативна документація»),
на сторінці стоїть посилання на той самий файл.

```bash
cd migration
python3 fixes-2026-09-25-library/push_assets.py --dry-run   # 3 файли
python3 fixes-2026-09-25-library/push_assets.py
```
