"""
m2port -- brings a modern spell model (MD21, versions 272 to 274, as wow.export
exports it in RAW) back to the 3.3.5a client (MD20, version 264).

    python m2port.py <model.m2 exported by wow.export> <output folder> <new name> [<game folder>]

The output folder receives <new name>.m2, <new name>00.skin and the textures,
each named after its source and FileDataID (shared between models). <game folder> is the folder of the client where
the files will live (default Spells\\LimitBreak): the model names its textures by
that path.

WHAT CHANGES, AND WHY (layouts from wowdev.wiki, M2 and SKIN pages):

- The chunked container goes: the MD20 inside it is kept byte for byte, its
  offsets being relative to its own start. Version 264.
- Textures: a modern model names them by FileDataID (chunk TXID); the 3.3.5
  client needs a path. The wow.export manifest gives each ID its exported file.
- Particle emitters: 492 bytes from Cataclysm on, 476 in 3.3.5. The last 16
  bytes (multiTextureParam0/1) go; the two bytes that became
  multiTextureParamX are particleType and headOrTail again; a texture packed
  three to a field keeps its first; a compressed gravity (flag 0x800000)
  becomes the scalar the old client pulls down with.
- Blend modes past 6 (7, "blend add") become 4 (add), the closest the old
  client has; render flags past 0x1F go.
- Header flags past 0x0F go; one skin profile only.
- Skins: the header of the old client stops at boneCountMax (48 bytes); the
  shadow batches that follow in a modern one are simply never read. Batches
  keep one texture and shader 0: the texture combiners of modern clients do
  not exist in 3.3.5.
- Sequences whose keys live in .anim files are not handled: the tool stops and
  says so (spell effects keep theirs in the model).

The new data (filenames, converted emitters) is appended to the MD20 blob and
the header arrays repointed; what it replaces stays, unused.
"""

import json
import os
import shutil
import struct
import sys

BEFORE_SKIN = ['global_loops', 'sequences', 'sequence_lookups', 'bones', 'key_bone_lookup', 'vertices']
AFTER_SKIN = ['colors', 'textures', 'texture_weights', 'texture_transforms', 'replaceable_texture_lookup',
              'materials', 'bone_lookup', 'texture_lookup', 'texture_unit_lookup', 'transparency_lookup',
              'texture_transform_lookup']
AFTER_BOX = ['collision_indices', 'collision_positions', 'collision_normals', 'attachments',
             'attachment_lookup', 'events', 'lights', 'cameras', 'camera_lookup',
             'ribbon_emitters', 'particle_emitters']

PARTICLE_MODERN = 492
PARTICLE_OLD = 476
SEQUENCE = 64
SEQ_EMBEDDED = 0x20


class Fault(Exception):
    pass


def chunks(b):
    off, out = 0, {}
    while off + 8 <= len(b):
        tag, size = struct.unpack_from('<4sI', b, off)
        out.setdefault(tag.decode('latin1'), []).append((off + 8, size))
        off += 8 + size
    return out


def header_layout(md):
    """Offsets (in the blob) of each header field of a version >= 264 model."""
    fields = {}
    p = 8
    fields['name'] = p; p += 8
    fields['flags'] = p; p += 4
    for n in BEFORE_SKIN:
        fields[n] = p; p += 8
    fields['num_skin'] = p; p += 4
    for n in AFTER_SKIN:
        fields[n] = p; p += 8
    p += 4 * 14
    for n in AFTER_BOX:
        fields[n] = p; p += 8
    flags = struct.unpack_from('<I', md, fields['flags'])[0]
    if flags & 0x8:
        fields['texture_combiner_combos'] = p; p += 8
    return fields, p


def array(md, fields, name):
    return struct.unpack_from('<II', md, fields[name])


def set_array(md, fields, name, count, ofs):
    struct.pack_into('<II', md, fields[name], count, ofs)


def append(md, data, align=16):
    while len(md) % align:
        md.append(0)
    ofs = len(md)
    md.extend(data)
    return ofs


def convert_gravity(md, track_ofs):
    """Compressed gravity (int8 x, int8 y, int16 z) -> the scalar of 3.3.5,
    pulling down: the opposite of the vertical part of the vector."""
    _, _, _, _, vcount, vofs = struct.unpack_from('<HhIIII', md, track_ofs)
    for i in range(vcount):
        n, o = struct.unpack_from('<II', md, vofs + i * 8)
        for k in range(n):
            x, y, z = struct.unpack_from('<bbh', md, o + k * 4)
            dx, dy = x / 128.0, y / 128.0
            dz = max(0.0, 1.0 - dx * dx - dy * dy) ** 0.5
            mag = z * 0.04238648
            if mag < 0:
                dz, mag = -dz, -mag
            struct.pack_into('<f', md, o + k * 4, -(dz * mag))


def port(src, outdir, newname, gamedir='Spells\\LimitBreak'):
    b = open(src, 'rb').read()
    if b[:4] != b'MD21':
        raise Fault('not a modern (MD21) model')
    ch = chunks(b)
    off, size = ch['MD21'][0]
    md = bytearray(b[off:off + size])
    version = struct.unpack_from('<I', md, 4)[0]
    if not 272 <= version <= 274:
        raise Fault(f'version {version}: 272 to 274 handled')
    fields, _ = header_layout(md)

    manifest_path = os.path.splitext(src)[0] + '.manifest.json'
    manifest = json.load(open(manifest_path, encoding='utf-8'))
    srcdir = os.path.dirname(src)
    tex_files = {t['fileDataID']: os.path.normpath(os.path.join(srcdir, t['file'])) for t in manifest['textures']}

    txid = []
    if 'TXID' in ch:
        o, s = ch['TXID'][0]
        txid = list(struct.unpack_from('<%dI' % (s // 4), b, o))

    report = []
    os.makedirs(outdir, exist_ok=True)

    # --- sequences: keys must be in the model --------------------------------
    scount, sofs = array(md, fields, 'sequences')
    for i in range(scount):
        sflags = struct.unpack_from('<I', md, sofs + i * SEQUENCE + 12)[0]
        if not sflags & SEQ_EMBEDDED:
            raise Fault(f'sequence {i} keeps its keys in an .anim file: not handled')
        struct.pack_into('<I', md, sofs + i * SEQUENCE + 12, sflags & 0x7F)

    # --- textures: a path for each FileDataID -------------------------------
    tcount, tofs = array(md, fields, 'textures')
    for i in range(tcount):
        ttype, tflags, fnlen, fnofs = struct.unpack_from('<IIII', md, tofs + i * 16)
        if ttype != 0:
            continue                             # replaceable texture: no file
        fid = txid[i] if i < len(txid) else 0
        source = tex_files.get(fid)
        if not source or not os.path.exists(source):
            report.append(f'texture {i} (FileDataID {fid}) missing from the export')
            continue
        # one file per source texture, shared by every model that uses it:
        # its name, made unique by its FileDataID
        base = os.path.splitext(os.path.basename(source))[0].lower()
        target = base + '.blp' if base.endswith(str(fid)) else f'{base}_{fid}.blp'
        shutil.copyfile(source, os.path.join(outdir, target))
        path = (gamedir + '\\' + target).encode('ascii') + b'\0'
        sofs_ = append(md, path, 4)
        struct.pack_into('<IIII', md, tofs + i * 16, ttype, tflags, len(path), sofs_)

    # --- materials: blend modes and flags of 3.3.5 --------------------------
    mcount, mofs = array(md, fields, 'materials')
    for i in range(mcount):
        mflags, blend = struct.unpack_from('<HH', md, mofs + i * 4)
        struct.pack_into('<HH', md, mofs + i * 4, mflags & 0x1F, blend if blend <= 6 else 4)

    # --- particle emitters: 492 bytes -> 476 --------------------------------
    pcount, pofs = array(md, fields, 'particle_emitters')
    if pcount:
        out = bytearray()
        for i in range(pcount):
            rec = md[pofs + i * PARTICLE_MODERN: pofs + (i + 1) * PARTICLE_MODERN]
            flags = struct.unpack_from('<I', rec, 4)[0]
            if flags & 0x800000:
                convert_gravity(md, pofs + i * PARTICLE_MODERN + 132)
                rec = md[pofs + i * PARTICLE_MODERN: pofs + (i + 1) * PARTICLE_MODERN]
            new = bytearray(rec[:PARTICLE_OLD])
            if flags & 0x10000000:
                tex = struct.unpack_from('<H', new, 22)[0]
                struct.pack_into('<H', new, 22, tex & 0x1F)
            if new[40] > 4:
                new[40] = 4
            head = struct.unpack_from('<I', new, 316)[0]
            tail = struct.unpack_from('<I', new, 332)[0]
            new[44] = 0
            new[45] = 1 if (tail and not head) else 0
            struct.pack_into('<I', new, 4, flags & 0x007FFFFF)
            out += new
        set_array(md, fields, 'particle_emitters', pcount, append(md, out))

    # --- header --------------------------------------------------------------
    struct.pack_into('<I', md, 4, 264)
    flags = struct.unpack_from('<I', md, fields['flags'])[0]
    struct.pack_into('<I', md, fields['flags'], flags & 0x0F)
    struct.pack_into('<I', md, fields['num_skin'], 1)
    name = newname.encode('ascii') + b'\0'
    set_array(md, fields, 'name', len(name), append(md, name, 4))

    open(os.path.join(outdir, newname + '.m2'), 'wb').write(md)

    # --- skin ---------------------------------------------------------------
    skin_src = os.path.join(srcdir, manifest['skins'][0]['file'])
    skin = bytearray(open(skin_src, 'rb').read())
    if skin[:4] != b'SKIN':
        raise Fault('skin without its SKIN magic')
    scount_, sofs_ = struct.unpack_from('<II', skin, 4 + 8 * 3)
    bcount, bofs = struct.unpack_from('<II', skin, 4 + 8 * 4)
    for i in range(bcount):
        o = bofs + i * 24
        skin[o] &= 0x1F                                         # flags of 3.3.5
        tex_count = struct.unpack_from('<H', skin, o + 14)[0]
        struct.pack_into('<H', skin, o + 2, 0)                  # shader_id
        if tex_count > 1:
            struct.pack_into('<H', skin, o + 14, 1)             # textureCount
    # boneCountMax: modern skins leave it at 0, the old client needs the most
    # bones a submesh uses (21 at least, its usual value)
    most = 21
    for i in range(scount_):
        most = max(most, struct.unpack_from('<H', skin, sofs_ + i * 48 + 12)[0])
    struct.pack_into('<I', skin, 4 + 8 * 5, max(struct.unpack_from('<I', skin, 4 + 8 * 5)[0], most))
    open(os.path.join(outdir, newname + '00.skin'), 'wb').write(skin)

    return report


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    try:
        notes = port(*sys.argv[1:5])
    except Fault as e:
        print('FAILED:', e)
        sys.exit(2)
    for n in notes:
        print('note:', n)
    print('ok')
