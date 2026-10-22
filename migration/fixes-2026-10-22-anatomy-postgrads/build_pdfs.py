#!/usr/bin/env python3
"""
Зібрати PDF-картки двох аспірантів кафедри анатомії (правки 22.10): фото ліворуч, текст
праворуч. Текст — дослівно з .docx, надісланих кафедрою (лист 21.10, 22:01).

Потрібен reportlab і шрифт DejaVu Serif (кирилиця):

    docker run --rm -v "$PWD":/b -v /usr/share/fonts/truetype/dejavu:/fonts:ro -w /b \
      python:3.12-slim sh -c 'pip install -q reportlab && python3 build_pdfs.py'

Результат — `files/anatomy-postgrad-*.pdf`; їх заливає `push_assets.py`.
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit

HERE = Path(__file__).parent
FILES = HERE / 'files'
FONTS = Path('/fonts')

pdfmetrics.registerFont(TTFont('Serif', str(FONTS / 'DejaVuSerif.ttf')))
pdfmetrics.registerFont(TTFont('Serif-Bold', str(FONTS / 'DejaVuSerif-Bold.ttf')))

CARDS = [
    {
        'photo': 'anatomy-postgrad-mineiev.jpg',
        'pdf': 'anatomy-postgrad-mineiev.pdf',
        'name': 'Мінєєв Макарій Максимович',
        'lines': [
            'Тема дисертації: Показники фізичного розвитку та функціонального стану учнів в '
            'умовах змішаного навчання.',
            'Спеціальність: Е1 Біологія та біохімія.',
            'Форма навчання: денна',
            'Роки навчання: 2025 - 2029.',
            'Науковий керівник: Комісова Тетяна Євгеніївна, кандидат біологічних наук, професор.',
        ],
    },
    {
        'photo': 'anatomy-postgrad-shelekhan.jpg',
        'pdf': 'anatomy-postgrad-shelekhan.pdf',
        'name': 'Шелехань Артем Анатолійович',
        'lines': [
            'Тема дисертації: «Динаміка психофізіологічних показників підлітків-ВПО на різних '
            'етапах адаптації»',
            'Спеціальність - Е1 Біологія та біохімія',
            'Форма навчання денна',
            'Роки навчання - 2025 - 2029',
            'Науковий керівник: Комісова Тетяна Євгенівна, кандидат біологічних наук, професор',
        ],
    },
]

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 2 * cm
PHOTO_H = PAGE_H - 2 * MARGIN
GAP = 1 * cm


def build(card: dict) -> None:
    c = canvas.Canvas(str(FILES / card['pdf']), pagesize=(PAGE_W, PAGE_H))
    c.setTitle(card['name'])

    photo = ImageReader(str(FILES / card['photo']))
    iw, ih = photo.getSize()
    photo_w = PHOTO_H * iw / ih
    c.drawImage(photo, MARGIN, MARGIN, photo_w, PHOTO_H)

    x = MARGIN + photo_w + GAP
    width = PAGE_W - MARGIN - x
    y = PAGE_H - MARGIN - 14

    c.setFont('Serif-Bold', 16)
    for line in simpleSplit(card['name'], 'Serif-Bold', 16, width):
        c.drawString(x, y, line)
        y -= 22
    y -= 10

    c.setFont('Serif', 12)
    for text in card['lines']:
        for line in simpleSplit(text, 'Serif', 12, width):
            c.drawString(x, y, line)
            y -= 18
        y -= 8

    c.showPage()
    c.save()


for card in CARDS:
    build(card)
    print('ok', card['pdf'])
