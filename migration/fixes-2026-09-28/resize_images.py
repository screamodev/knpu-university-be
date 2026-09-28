"""
Стиснути фото цього бандла до JPEG ≤1600 px (довша сторона).

На цій машині немає macOS `sips` (був у бандлі 16.09) і немає Pillow в системному Python, тож
ресайз робимо в одноразовому контейнері `python:3.12-slim` з Pillow, поставленим з PyPI.
Джерело → назва в `files/`, як домовились по цьому бандлу.

    python3 resize_images.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
FILES = HERE / 'files'
MAX_SIDE = 1600

# (джерело, назва в files/)
SOURCES = [
    (HERE / 'src' / 'kuklina.jpg', 'kafedra-korekciynoyi-psyhopedagogiky-kuklina.jpg'),
    (HERE / 'src' / 'miroshnychenko.jpg', 'kafedra-korekciynoyi-psyhopedagogiky-miroshnychenko.jpg'),
    (HERE / 'src' / 'foto-1.png', 'kafedra-specialnoyi-pedagogiky-universytetski-kafedry-1.jpg'),
    *[(HERE / 'src' / f'useful-link-{i:02d}.png', f'mental-health-centre-useful-link-{i:02d}.jpg')
      for i in range(1, 12)],
]

SCRIPT = '''
import sys
from pathlib import Path
from PIL import Image

src_dir, out_dir, max_side = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
for src in sorted(src_dir.iterdir()):
    im = Image.open(src).convert('RGB')
    w, h = im.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    im.save(out_dir / (src.stem + '.jpg'), 'JPEG', quality=82)
'''


def main() -> int:
    staging_in = HERE / '_resize_in'
    staging_out = HERE / '_resize_out'
    staging_in.mkdir(exist_ok=True)
    staging_out.mkdir(exist_ok=True)
    FILES.mkdir(exist_ok=True)

    todo = [(src, name) for src, name in SOURCES if src.exists() and not (FILES / name).exists()]
    if not todo:
        print('nothing to resize (already done or sources missing)')
        return 0

    for src, name in todo:
        shutil.copy(src, staging_in / (Path(name).stem + src.suffix))

    (HERE / '_resize.py').write_text(SCRIPT, encoding='utf-8')
    subprocess.run(
        ['docker', 'run', '--rm',
         '-v', f'{staging_in}:/in', '-v', f'{staging_out}:/out', '-v', f'{HERE}/_resize.py:/resize.py',
         'python:3.12-slim', 'bash', '-c',
         'pip install --quiet Pillow && python3 /resize.py /in /out ' + str(MAX_SIDE)],
        check=True,
    )
    (HERE / '_resize.py').unlink()

    for src, name in todo:
        out = staging_out / (Path(name).stem + '.jpg')
        shutil.copy(out, FILES / name)
        print('  ·', name)

    shutil.rmtree(staging_in)
    shutil.rmtree(staging_out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
