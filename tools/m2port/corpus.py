"""
corpus -- the spell models of the 3.3.5a client itself, as the reference of
what that client loads without harm.

    python corpus.py <game folder> <output folder>

Reads Blizzard's archives only (common, common-2, expansion, lichking, patch,
patch-2, patch-3, and the locale ones), the later ones overriding the earlier,
and writes every Spells\\*.m2 with its skins into <output folder>.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', '..', 'installer')))
import mpq_archive  # noqa: E402

BLIZZARD = ['common.mpq', 'common-2.mpq', 'expansion.mpq', 'lichking.mpq', 'patch.mpq', 'patch-2.mpq', 'patch-3.mpq']


def archives(game):
    data = os.path.join(game, 'Data')
    found = [os.path.join(data, n) for n in BLIZZARD if os.path.exists(os.path.join(data, n))]
    for loc in sorted(os.listdir(data)):
        sub = os.path.join(data, loc)
        if os.path.isdir(sub) and len(loc) == 4:
            for n in ('locale-%s.mpq', 'expansion-locale-%s.mpq', 'lichking-locale-%s.mpq',
                      'patch-%s.mpq', 'patch-%s-2.mpq', 'patch-%s-3.mpq'):
                p = os.path.join(sub, n % loc)
                if os.path.exists(p):
                    found.append(p)
    return found


def main(game, out):
    os.makedirs(out, exist_ok=True)
    latest = {}
    for path in archives(game):
        a = mpq_archive.Archive(path)
        try:
            names = a.read('(listfile)').decode('latin1').splitlines()
        except Exception:
            continue
        for n in names:
            low = n.lower()
            if low.startswith('spells\\') and (low.endswith('.m2') or low.endswith('.skin')):
                latest[low] = (a, n)
    count = 0
    for low, (a, n) in sorted(latest.items()):
        try:
            data = a.read(n)
        except Exception as e:
            print('unreadable', n, e)
            continue
        open(os.path.join(out, os.path.basename(low)), 'wb').write(data)
        count += 1
    print(count, 'files')


if __name__ == '__main__':
    main(*sys.argv[1:3])
