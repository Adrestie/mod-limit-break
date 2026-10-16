"""
pack -- a modern spell model, as export.py exported it, laid out for a client
with WarcraftXL and its modern M2 plugin (wxl-modern-m2), which reads modern
models natively: no conversion.

    python pack.py <model.m2> <output folder> <new name> [<game folder>]

The output folder receives, renamed after <new name>:
  - the model itself (MD21, its chunks untouched);
  - its views (<new name>00.skin...) and levels of detail (<new name>_lod01.skin...);
  - its external animations (<new name>AAAA-VV.anim);
  - its textures, under their exported names.

One change inside the model: the texture names. A modern model names its
textures only by FileDataID (TXID), which the plugin resolves through
WarcraftXL's FileDataID tables (wxl-db2) and draws solid white when it cannot;
the name of each texture's path in the game folder is written beside it, in
the texture's own filename field, so that the model holds both.
"""

import json
import os
import shutil
import struct
import sys

import tweak

TEXTURES_ARRAY = 8 + 8 + 4 + 6 * 8 + 4 + 8      # offset of the textures M2Array in MD20


class Fault(Exception):
    pass


def chunk_list(b):
    out, off = [], 0
    while off + 8 <= len(b):
        tag, size = struct.unpack_from('<4sI', b, off)
        out.append((tag, b[off + 8:off + 8 + size]))
        off += 8 + size
    return out


def name_textures(md, txid, names):
    """The MD20 blob with each texture's filename filled (appended at its end)."""
    md = bytearray(md)
    count, ofs = struct.unpack_from('<II', md, TEXTURES_ARRAY)
    for i in range(count):
        ttype, flags, length, sofs = struct.unpack_from('<IIII', md, ofs + i * 16)
        fid = txid[i] if i < len(txid) else 0
        if ttype != 0 or fid not in names:
            continue
        data = names[fid].encode('ascii') + b'\0'
        while len(md) % 4:
            md.append(0)
        pos = len(md)
        md += data
        struct.pack_into('<IIII', md, ofs + i * 16, ttype, flags, len(data), pos)
    return bytes(md)


def pack(src, outdir, newname, gamedir='Spells\\LimitBreak', options=None, remap=None):
    """options (visuals.json): time_scale, particle_speed, billboard_upright,
    remap_effects (with `remap`: modern shader ID -> replacement)."""
    options = options or {}
    notes = []
    b = open(src, 'rb').read()
    if b[:4] != b'MD21':
        raise Fault('not a modern (MD21) model')
    manifest = json.load(open(os.path.splitext(src)[0] + '.manifest.json', encoding='utf-8'))
    srcdir = os.path.dirname(src)
    os.makedirs(outdir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]

    names = {}
    for t in manifest['textures']:
        file = os.path.basename(t['file']).lower()
        shutil.copyfile(os.path.normpath(os.path.join(srcdir, t['file'])), os.path.join(outdir, file))
        names[t['fileDataID']] = gamedir + '\\' + file

    chunks = chunk_list(b)
    txid_raw = next((d for t, d in chunks if t == b'TXID'), b'')
    txid = list(struct.unpack('<%dI' % (len(txid_raw) // 4), txid_raw))
    out = bytearray()
    for tag, data in chunks:
        if tag == b'MD21':
            data = name_textures(data, txid, names)
            if options.get('time_scale'):
                data = tweak.retime(data, options['time_scale'])
            if options.get('particle_speed'):
                data = tweak.particle_speed(data, options['particle_speed'])
            if options.get('billboard_upright'):
                data, n = tweak.billboard_upright(data)
                notes.append(f'{n} billboard bone(s) made upright')
        out += struct.pack('<4sI', tag, len(data)) + data
    open(os.path.join(outdir, newname + '.m2'), 'wb').write(out)

    for s in manifest.get('skins', []) + manifest.get('lodSkins', []):
        target = newname + os.path.basename(s['file'])[len(stem):]
        skin = open(os.path.join(srcdir, s['file']), 'rb').read()
        if options.get('remap_effects') and remap:
            skin, n = tweak.remap_shaders(skin, remap)
            notes.append(f'{n} batch shader(s) remapped in {target}')
        open(os.path.join(outdir, target), 'wb').write(skin)
    for a in manifest.get('anims', []):
        target = newname + os.path.basename(a['file'])[len(stem):]
        shutil.copyfile(os.path.join(srcdir, a['file']), os.path.join(outdir, target))
    return notes


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    try:
        pack(*sys.argv[1:5])
    except Fault as e:
        print('FAILED:', e)
        sys.exit(2)
    print('ok')
