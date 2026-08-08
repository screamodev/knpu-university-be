#!/usr/bin/env python3
"""
Check that every legacy URL still resolves through the running site.

Reads `legacy_redirects` and asks the Nuxt server for each `legacyPath`: it must answer 301, and
the target must answer 200. This is the test that matters — the links are in the state
dissertation register, and «сторінку не знайдено» there is the failure this whole migration
exists to prevent.

    export DIRECTUS_URL=http://localhost:8055 SITE_URL=http://localhost:3000
    python3 5_check_redirects.py --sample 100      # spot check
    python3 5_check_redirects.py --kind page       # every page, follow every target
    python3 5_check_redirects.py                   # everything
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import urllib.error
import urllib.parse
import urllib.request

from shared import Directus, login


def head(url: str, timeout: int = 30) -> tuple[int, str]:
    """→ (status, Location). Redirects are the answer here, so never follow them."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, method='HEAD')
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.headers.get('Location', '')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get('Location', '')
    except (urllib.error.URLError, OSError) as exc:
        print(f'    ! {url}: {exc}', file=sys.stderr)
        return 0, ''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--site', default=os.environ.get('SITE_URL') or 'http://localhost:3000')
    parser.add_argument('--kind', choices=['page', 'file'], help='check only one kind')
    parser.add_argument('--sample', type=int, help='check a random sample of this many rows')
    parser.add_argument('--no-follow', action='store_true', help='do not verify the target answers 200')
    parser.add_argument('--directus-url', default=os.environ.get('DIRECTUS_URL') or 'http://localhost:8055')
    parser.add_argument('--token', default=(os.environ.get('DIRECTUS_TOKEN') or '').strip() or None)
    parser.add_argument('--email', default=os.environ.get('DIRECTUS_EMAIL') or 'admin@example.com')
    parser.add_argument('--password', default=os.environ.get('DIRECTUS_PASSWORD') or 'admin')
    args = parser.parse_args()

    token = args.token or login(args.directus_url, args.email, args.password)
    directus = Directus(args.directus_url, token)

    query = {'fields': 'legacyPath,targetPath,file,kind', 'limit': '-1'}
    if args.kind:
        query['filter[kind][_eq]'] = args.kind
    rows = directus.get('/items/legacy_redirects?' + urllib.parse.urlencode(query)) or []
    if args.sample and args.sample < len(rows):
        rows = random.sample(rows, args.sample)

    site = args.site.rstrip('/')
    bad: list[str] = []
    dead: list[str] = []

    for index, row in enumerate(rows, 1):
        path = row['legacyPath']
        status, location = head(site + urllib.parse.quote(path, safe='/%'))
        if status != 301 or not location:
            bad.append(f'{status} {path}')
        elif not args.no_follow:
            target_status, _ = head(location if location.startswith('http') else site + location)
            if target_status != 200:
                dead.append(f'{target_status} {path} → {location}')
        if index % 100 == 0:
            print(f'  [{index}/{len(rows)}] bad={len(bad)} dead={len(dead)}', file=sys.stderr)

    print(f'\nchecked={len(rows)} not_redirected={len(bad)} target_broken={len(dead)}', file=sys.stderr)
    for line in bad[:20]:
        print(f'  ! {line}', file=sys.stderr)
    for line in dead[:20]:
        print(f'  ✗ {line}', file=sys.stderr)
    return 1 if bad or dead else 0


if __name__ == '__main__':
    raise SystemExit(main())
