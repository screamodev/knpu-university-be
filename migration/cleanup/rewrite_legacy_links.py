#!/usr/bin/env python3
"""
Перевести посилання на старий сайт з `hnpu.edu.ua` на `old.hnpu.edu.ua`.

Поки новий сайт живе на `hnpu.dev42hub.uk`, посилання в перенесеному контенті ведуть на
`https://hnpu.edu.ua/...` — тобто на старий сайт, і це правильно. Після переїзду на домен
університету за цією адресою стоятиме вже новий сайт, а старі сторінки — на `old.hnpu.edu.ua`.
Тому перед перемиканням DNS усі такі посилання треба переписати.

Що скрипт чіпає і чого не чіпає:

* переписує тільки хости `hnpu.edu.ua` і `www.hnpu.edu.ua` — піддомени (`smc.`, `lms.`,
  `dspace.`, `journals.`, `library.`, `catalog.`) лишаються, вони живуть на своїх серверах;
* не чіпає адрес пошти (`@hnpu.edu.ua`) і Google-сайтів (`sites.google.com/hnpu.edu.ua/...`);
* окрім перенесеного контенту, проходить і по коду (`.ts`/`.vue`) — там ті самі адреси стоять
  у константах `externalSites.ts` і в кількох списках посилань.

    python3 rewrite_legacy_links.py --dry-run
    python3 rewrite_legacy_links.py
    python3 rewrite_legacy_links.py --revert        # назад, якщо переїзд відкладено
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve()
FRONTEND = HERE.parents[3] / 'knpu-university-fe' / 'app'

#: Де живе перенесений контент, підписи інтерфейсу й код із посиланнями.
SEARCH_GLOBS = ['content/**/*.json', 'locales/*.json', 'utils/*.ts', 'pages/**/*.vue',
                'components/**/*.vue', 'composables/*.ts']

OLD_HOST = 'hnpu.edu.ua'
NEW_HOST = 'old.hnpu.edu.ua'

#: `https://hnpu.edu.ua`, `http://www.hnpu.edu.ua`, `//hnpu.edu.ua` — але не `smc.hnpu.edu.ua`
#: і не `sites.google.com/hnpu.edu.ua`, бо перед хостом там немає роздільника схеми.
LINK_RE = re.compile(r'(?P<scheme>https?:\\?/\\?/|(?<![:/\w.])//)(?:www\.)?hnpu\.edu\.ua(?=[/"\'\\\s<)\]]|$)')
REVERT_RE = re.compile(r'(?P<scheme>https?:\\?/\\?/|(?<![:/\w.])//)old\.hnpu\.edu\.ua(?=[/"\'\\\s<)\]]|$)')


def files() -> list[Path]:
    found: list[Path] = []
    for pattern in SEARCH_GLOBS:
        found += [path for path in FRONTEND.glob(pattern) if path.is_file()]
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--revert', action='store_true', help='old.hnpu.edu.ua → hnpu.edu.ua')
    args = parser.parse_args()

    pattern = REVERT_RE if args.revert else LINK_RE
    target = OLD_HOST if args.revert else NEW_HOST

    touched = 0
    total = 0
    for path in files():
        text = path.read_text(encoding='utf-8')
        replaced, count = pattern.subn(lambda m: m.group('scheme') + target, text)
        if not count:
            continue
        touched += 1
        total += count
        print(f'{count:>4}  {path.relative_to(FRONTEND.parent)}')
        if not args.dry_run:
            path.write_text(replaced, encoding='utf-8')

    print(f'\n{total} посилань у {touched} файлах')
    print('сухий прогін — нічого не записано.' if args.dry_run else 'готово.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
