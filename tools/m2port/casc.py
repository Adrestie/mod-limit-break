"""
casc -- reads files out of a local installation of the modern game (CASC), by
FileDataID, without wow.export.

    python casc.py <install folder> <FileDataID> <output file>

Layouts from wowdev.wiki (CASC, BLTE, Encoding, Root, TACT). Read-only: the
installation is never written. Encrypted blocks ('E') are not decrypted; a file
that holds one is reported as unreadable.
"""

import bisect
import glob
import hashlib  # noqa: F401  (kept for checks while debugging)
import os
import struct
import sys
import zlib


class CascError(Exception):
    pass


def blte(data):
    """The content of a BLTE stream."""
    if data[:4] != b'BLTE':
        raise CascError('not BLTE')
    header_size = struct.unpack_from('>I', data, 4)[0]
    if header_size == 0:
        return decode_block(data[8:])
    flags = data[8]
    count = int.from_bytes(data[9:12], 'big')
    pos = 12
    blocks = []
    for _ in range(count):
        comp, decomp = struct.unpack_from('>II', data, pos)
        pos += 8 + 16
        blocks.append((comp, decomp))
    if flags != 0x0F:
        raise CascError(f'BLTE flags {flags:#x}')
    out = bytearray()
    pos = header_size
    for comp, decomp in blocks:
        out += decode_block(data[pos:pos + comp])
        pos += comp
    return bytes(out)


def decode_block(block):
    mode = block[:1]
    if mode == b'N':
        return block[1:]
    if mode == b'Z':
        return zlib.decompress(block[1:])
    if mode == b'F':
        return blte(block[1:])
    if mode == b'E':
        raise CascError('encrypted block')
    raise CascError(f'BLTE block mode {mode!r}')


def _rot(x, k):
    return ((x << k) | (x >> (32 - k))) & 0xFFFFFFFF


def hashlittle2(data, pc=0, pb=0):
    """Bob Jenkins' lookup3 hashlittle2: (pc, pb)."""
    length = len(data)
    a = b = c = (0xDEADBEEF + length + pc) & 0xFFFFFFFF
    c = (c + pb) & 0xFFFFFFFF
    i = 0
    while length > 12:
        a = (a + struct.unpack_from('<I', data, i)[0]) & 0xFFFFFFFF
        b = (b + struct.unpack_from('<I', data, i + 4)[0]) & 0xFFFFFFFF
        c = (c + struct.unpack_from('<I', data, i + 8)[0]) & 0xFFFFFFFF
        a = (a - c) & 0xFFFFFFFF; a ^= _rot(c, 4); c = (c + b) & 0xFFFFFFFF
        b = (b - a) & 0xFFFFFFFF; b ^= _rot(a, 6); a = (a + c) & 0xFFFFFFFF
        c = (c - b) & 0xFFFFFFFF; c ^= _rot(b, 8); b = (b + a) & 0xFFFFFFFF
        a = (a - c) & 0xFFFFFFFF; a ^= _rot(c, 16); c = (c + b) & 0xFFFFFFFF
        b = (b - a) & 0xFFFFFFFF; b ^= _rot(a, 19); a = (a + c) & 0xFFFFFFFF
        c = (c - b) & 0xFFFFFFFF; c ^= _rot(b, 4); b = (b + a) & 0xFFFFFFFF
        length -= 12
        i += 12
    if length == 0:
        return c, b
    tail = data[i:] + bytes(12 - length)
    a = (a + struct.unpack_from('<I', tail, 0)[0]) & 0xFFFFFFFF
    b = (b + struct.unpack_from('<I', tail, 4)[0]) & 0xFFFFFFFF
    c = (c + struct.unpack_from('<I', tail, 8)[0]) & 0xFFFFFFFF
    c ^= b; c = (c - _rot(b, 14)) & 0xFFFFFFFF
    a ^= c; a = (a - _rot(c, 11)) & 0xFFFFFFFF
    b ^= a; b = (b - _rot(a, 25)) & 0xFFFFFFFF
    c ^= b; c = (c - _rot(b, 16)) & 0xFFFFFFFF
    a ^= c; a = (a - _rot(c, 4)) & 0xFFFFFFFF
    b ^= a; b = (b - _rot(a, 14)) & 0xFFFFFFFF
    c ^= b; c = (c - _rot(b, 24)) & 0xFFFFFFFF
    return c, b


def name_hash(path):
    c, b = hashlittle2(path.replace('/', chr(92)).upper().encode('ascii'))
    return (c << 32) | b


class Casc:
    def __init__(self, install, product='wow'):
        self.data_dir = os.path.join(install, 'Data')
        self.build = self._build_config(install, product)
        self._load_indices()
        enc_ckey, enc_ekey = self.build['encoding'].split()
        self._load_encoding(bytes.fromhex(enc_ekey))
        self._root = None
        self._root_ckey = bytes.fromhex(self.build['root'].split()[0])

    # --- configuration ------------------------------------------------------
    def _build_config(self, install, product):
        def read(path):
            conf = {}
            for l in open(path, encoding='utf-8', errors='replace'):
                if ' = ' in l:
                    k, v = l.strip().split(' = ', 1)
                    conf[k] = v
            return conf

        lines = open(os.path.join(install, '.build.info'), encoding='utf-8').read().splitlines()
        names = [h.split('!')[0] for h in lines[0].split('|')]
        for line in lines[1:]:
            row = dict(zip(names, line.split('|')))
            if row.get('Product') == product and row.get('Active') == '1':
                key = row['Build Key']
                return read(os.path.join(self.data_dir, 'config', key[:2], key[2:4], key))
        # the launcher drops a product from .build.info while it updates it: the
        # newest build configuration of that product left in Data\config serves
        marker = {'wow': '_Retail', 'wow_classic_beta': 'Classic'}.get(product, product)
        found = []
        for path in glob.glob(os.path.join(self.data_dir, 'config', '*', '*', '*')):
            try:
                conf = read(path)
            except OSError:
                continue
            if marker in conf.get('build-name', '') and 'root' in conf and 'encoding' in conf:
                found.append((os.path.getmtime(path), conf))
        if found:
            return max(found, key=lambda x: x[0])[1]
        raise CascError(f'no build of product {product}')

    # --- local indices: encoding key (9 bytes) -> archive, offset, size ------
    def _load_indices(self):
        latest = {}
        for path in glob.glob(os.path.join(self.data_dir, 'data', '*.idx')):
            name = os.path.basename(path)
            bucket, version = int(name[:2], 16), int(name[2:10], 16)
            if bucket not in latest or version > latest[bucket][0]:
                latest[bucket] = (version, path)
        self.index = {}
        for _, path in latest.values():
            b = open(path, 'rb').read()
            header_size = struct.unpack_from('<I', b, 0)[0]
            pos = 8 + header_size
            pos = (pos + 15) & ~15
            entries_size = struct.unpack_from('<I', b, pos)[0]
            pos += 8
            for e in range(pos, pos + entries_size, 18):
                key = b[e:e + 9]
                packed = int.from_bytes(b[e + 9:e + 14], 'big')
                size = struct.unpack_from('<I', b, e + 14)[0]
                if key not in self.index:
                    self.index[key] = (packed >> 30, packed & 0x3FFFFFFF, size)

    def read_ekey(self, ekey):
        loc = self.index.get(ekey[:9])
        if not loc:
            raise CascError(f'encoding key {ekey.hex()} not in the local storage')
        archive, offset, size = loc
        with open(os.path.join(self.data_dir, 'data', f'data.{archive:03d}'), 'rb') as f:
            f.seek(offset + 30)
            return blte(f.read(size - 30))

    # --- encoding: content key -> encoding key ------------------------------
    def _load_encoding(self, ekey):
        b = self.read_ekey(ekey)
        if b[:2] != b'EN':
            raise CascError('encoding without its magic')
        ckey_size, ekey_size = b[3], b[4]
        ce_page_kb = struct.unpack_from('>H', b, 5)[0]
        ce_pages = struct.unpack_from('>I', b, 9)[0]
        espec_size = struct.unpack_from('>I', b, 18)[0]
        pos = 22 + espec_size
        self._enc_first = []
        for i in range(ce_pages):
            self._enc_first.append(b[pos:pos + ckey_size])
            pos += ckey_size + 16
        self._enc_pages = pos
        self._enc_page_size = ce_page_kb * 1024
        self._enc = b
        self._ckey_size, self._ekey_size = ckey_size, ekey_size

    def ekey_of(self, ckey):
        i = bisect.bisect_right(self._enc_first, ckey) - 1
        if i < 0:
            raise CascError('content key before the first page')
        b = self._enc
        pos = self._enc_pages + i * self._enc_page_size
        end = pos + self._enc_page_size
        while pos < end:
            count = b[pos]
            if count == 0:
                break
            ck = b[pos + 6:pos + 6 + self._ckey_size]
            if ck == ckey:
                p = pos + 6 + self._ckey_size
                return b[p:p + self._ekey_size]
            pos += 6 + self._ckey_size + count * self._ekey_size
        raise CascError(f'content key {ckey.hex()} not in the encoding')

    def read_ckey(self, ckey):
        return self.read_ekey(self.ekey_of(ckey))

    # --- root: FileDataID -> content key ------------------------------------
    def _load_root(self):
        b = self.read_ckey(self._root_ckey)
        root = {}
        self._names = {}
        pos = 0
        version = 0
        if b[:4] == b'TSFM':
            header_size, version = struct.unpack_from('<II', b, 4)
            if header_size < 0x18:              # older layout: no header size
                header_size, version = 12, 1
            pos = header_size
        while pos < len(b):
            count = struct.unpack_from('<I', b, pos)[0]
            if version >= 2:
                locale, f1, f2, f3 = struct.unpack_from('<IIIB', b, pos + 4)[:4]
                content = f1 | f2 | (f3 << 17)
                pos += 17
            else:
                content, locale = struct.unpack_from('<II', b, pos + 4)
                pos += 12
            fid = -1
            ids = []
            for k in range(count):
                fid += struct.unpack_from('<i', b, pos + 4 * k)[0] + 1
                ids.append(fid)
            pos += 4 * count
            ckeys = [b[pos + 16 * k:pos + 16 * (k + 1)] for k in range(count)]
            pos += 16 * count
            if not content & 0x10000000:       # names present
                for k in range(count):
                    self._names[struct.unpack_from('<Q', b, pos + 8 * k)[0]] = ids[k]
                pos += 8 * count
            for fid_, ck in zip(ids, ckeys):
                if fid_ not in root or locale & 0x2:   # prefer enUS
                    root[fid_] = ck
        self._root = root

    def fid_of(self, path):
        """The FileDataID of a path, by the name hashes of the root (when the
        build still has them for that file)."""
        if self._root is None:
            self._load_root()
        return self._names.get(name_hash(path))

    def read_fid(self, fid):
        if self._root is None:
            self._load_root()
        ck = self._root.get(fid)
        if ck is None:
            raise CascError(f'FileDataID {fid} not in the root')
        return self.read_ckey(ck)


if __name__ == '__main__':
    c = Casc(sys.argv[1])
    data = c.read_fid(int(sys.argv[2]))
    open(sys.argv[3], 'wb').write(data)
    print(len(data), 'bytes')
