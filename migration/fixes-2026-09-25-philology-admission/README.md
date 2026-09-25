# Правки 25.09.2026 (п. 12) — ННІ української філології, «Вступнику»

Google Doc клієнта «Правки 25.09.26», п. 12: замінити фото й підпис під ним на вкладці
«Вступнику» (`app/content/structure/ukrainian-philology/admission.uk.json`). Файл — `2.jpg` з
пошти, новий рекламний постер інституту.

```bash
cd migration
python3 fixes-2026-09-25-philology-admission/push_assets.py --dry-run   # 1 файл
python3 fixes-2026-09-25-philology-admission/push_assets.py
```

Фото 940×788 — вже в межах 1600 px, стиснуто лише якістю (JPEG q82, текст на постері має
лишатись читабельним).
