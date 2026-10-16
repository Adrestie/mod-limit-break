"""
cdn -- reads files of the modern game from Blizzard's CDN (TACT), by
FileDataID, without a local installation: the same reader as casc.py, its
bytes fetched over HTTP and kept in a cache folder.

    python cdn.py <cache folder> <FileDataID> <output file>

What is downloaded, once, into the cache: the build and CDN configurations
(a few KB), the encoding and root files (some 200 MB together), and the
indices of the CDN archives (one per archive, some 300 MB together); then,
per file, only its own bytes (an HTTP range of its archive). Layouts from
wowdev.wiki (TACT, CDN archive indices).
"""

import bisect
import concurrent.futures
import os
import struct
import sys
import urllib.request

from casc import Casc, CascError, blte

PRODUCT = 'wow'
PATCH = 'http://us.patch.battle.net:1119'


def http(url, rng=None, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'Range': 'bytes=%d-%d' % rng} if rng else {})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:                    # noqa: BLE001
            if attempt == tries - 1:
                raise CascError(f'{url}: {e}')


def table(text):
    lines = [l for l in text.splitlines() if l and not l.startswith('##')]
    names = [h.split('!')[0] for h in lines[0].split('|')]
    return [dict(zip(names, l.split('|'))) for l in lines[1:]]


def config(text):
    conf = {}
    for l in text.splitlines():
        if ' = ' in l:
            k, v = l.split(' = ', 1)
            conf[k] = v
    return conf


class Cdn(Casc):
    def __init__(self, cache, region='eu'):
        self.cache = cache
        os.makedirs(cache, exist_ok=True)
        versions = next(r for r in table(http(f'{PATCH}/{PRODUCT}/versions').decode()) if r['Region'] == region)
        cdns = next(r for r in table(http(f'{PATCH}/{PRODUCT}/cdns').decode()) if r['Name'] == region)
        self.hosts = cdns['Hosts'].split()
        self.path = cdns['Path']
        self.build = config(self.fetch('config', versions['BuildConfig']).decode())
        self.cdn_config = config(self.fetch('config', versions['CDNConfig']).decode())
        self.archives = self.cdn_config['archives'].split()
        self.located = {}                         # ekey -> (archive or None for loose, offset, size)
        enc_ckey, enc_ekey = self.build['encoding'].split()
        self._load_encoding(bytes.fromhex(enc_ekey))
        self._root = None
        self._root_ckey = bytes.fromhex(self.build['root'].split()[0])

    # --- the CDN, through the cache -----------------------------------------
    def url(self, kind, h):
        return f'http://{self.hosts[0]}/{self.path}/{kind}/{h[:2]}/{h[2:4]}/{h}'

    def fetch(self, kind, h, suffix=''):
        path = os.path.join(self.cache, kind, h + suffix)
        if os.path.exists(path):
            return open(path, 'rb').read()
        data = http(self.url(kind, h) + suffix)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path + '.part', 'wb').write(data)
        os.replace(path + '.part', path)
        return data

    # --- where an encoding key lives ----------------------------------------
    def locate(self, ekeys):
        """Finds the archive of each encoding key, scanning the archive
        indices (downloaded once); keys in none are loose files."""
        wanted = {k for k in ekeys if k not in self.located}
        if not wanted:
            return
        for archive, data, toc in self.indices():
            for key in list(wanted):
                # the block whose last key is the first one at or past ours
                b = bisect.bisect_left(toc, key)
                if b >= len(toc):
                    continue
                base = b * 4096
                for e in range(170):
                    pos = base + e * 24
                    k = data[pos:pos + 16]
                    if k == key:
                        size, offset = struct.unpack_from('>II', data, pos + 16)
                        self.located[key] = (archive, offset, size)
                        wanted.discard(key)
                        break
                    if k > key or not any(k):
                        break
            if not wanted:
                break
        for k in wanted:
            self.located[k] = (None, 0, 0)

    def indices(self):
        """Every archive index, with the last key of each of its blocks (the
        table of contents that follows the blocks)."""
        if getattr(self, '_indices', None) is None:
            with concurrent.futures.ThreadPoolExecutor(8) as pool:
                raw = list(pool.map(lambda a: (a, self.fetch('data', a, '.index')), self.archives))
            self._indices = []
            for archive, data in raw:
                blocks = (len(data) - 28) // (4096 + 24)
                start = blocks * 4096
                toc = [data[start + 16 * i:start + 16 * (i + 1)] for i in range(blocks)]
                self._indices.append((archive, data, toc))
        return self._indices

    def read_ekey(self, ekey):
        if len(ekey) == 16 and ekey not in self.located:
            self.locate({ekey})
        archive, offset, size = self.located.get(ekey, (None, 0, 0))
        if archive is None:
            return blte(self.fetch('data', ekey.hex()))
        return blte(http(self.url('data', archive), (offset, offset + size - 1)))

    def read_ckey(self, ckey):
        return self.read_ekey(self.ekey_of(ckey))

    def prefetch(self, fids):
        """Locates the archives of several files in one scan of the indices."""
        if self._root is None:
            self._load_root()
        keys = set()
        for fid in fids:
            ck = self._root.get(fid)
            if ck is not None:
                try:
                    keys.add(self.ekey_of(ck))
                except CascError:
                    pass
        self.locate(keys)

    def _load_encoding(self, ekey):
        # the encoding file is loose on the CDN
        self.located[ekey] = (None, 0, 0)
        super()._load_encoding(ekey)


if __name__ == '__main__':
    c = Cdn(sys.argv[1])
    data = c.read_fid(int(sys.argv[2]))
    open(sys.argv[3], 'wb').write(data)
    print(len(data), 'bytes')
