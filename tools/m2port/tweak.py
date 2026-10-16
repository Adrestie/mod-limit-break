"""
tweak -- edits made in place in a modern model (the MD20 blob of an MD21 file)
and its skin, without changing their layout: only values are rewritten, so the
file stays what WarcraftXL's modern M2 plugin reads.

- retime(md, factor): every animation runs `factor` times longer (sequence
  durations, global loops, the keys of every track);
- particle_speed(md, factor): particles move `factor` times as fast and live
  1/factor as long (the same path, travelled at another speed);
- billboard_upright(md): bones that face the camera on every axis turn about
  the vertical axis only (they stay upright);
- remap_shaders(skin, table): batch shader IDs replaced (modern effects the
  plugin draws badly -> a combination it draws).

Only keys stored in the model are touched: sequences whose keys live in .anim
files are left as they are (none of the module's visuals has any).
"""

import struct

import m2

SEQ_DURATION = 4
BONE_FLAGS = 4
BILLBOARD_ALL = 0x8                 # spherical billboard
BILLBOARD_UPRIGHT = 0x40            # cylindrical, about Z
BILLBOARD_MASK = 0x8 | 0x10 | 0x20 | 0x40


def header_refs(md):
    p = 8 + 8
    flags = struct.unpack_from('<I', md, p)[0]
    p += 4
    refs = {}
    for name, t in m2.HEADER_BEFORE_SKIN:
        refs[name] = (struct.unpack_from('<II', md, p), t, p)
        p += 8
    p += 4
    for name, t in m2.HEADER_AFTER_SKIN:
        refs[name] = (struct.unpack_from('<II', md, p), t, p)
        p += 8
    p += 56
    for name, t in m2.HEADER_AFTER_BOX:
        refs[name] = (struct.unpack_from('<II', md, p), t, p)
        p += 8
    return refs, flags


def walk_tracks(md, modern=True):
    """Yields (record type, field, value type, track offset) for every track
    of every record of the header arrays."""
    refs, _ = header_refs(md)
    psize = 492 if modern else 476
    for name, ((count, ofs), t, _) in refs.items():
        if t not in m2.STRUCTS or name == 'cameras':
            continue
        size = psize if t == 'particle' else m2.SIZES[t]
        for i in range(count):
            base = ofs + i * size
            p = base
            for field, kind, arg in m2.STRUCTS[t]:
                if kind in ('track', 'trackbase'):
                    yield t, field, arg, p, kind == 'track'
                p += {'v': lambda: m2.vsize(arg), 'raw': lambda: arg, 'arr': lambda: 8, 'track': lambda: 20,
                      'trackbase': lambda: 12, 'fblock': lambda: 16}[kind]()


def embedded(md):
    refs, _ = header_refs(md)
    (count, ofs), _, _ = refs['sequences']
    return [bool(struct.unpack_from('<I', md, ofs + i * 64 + 12)[0] & m2.EMBEDDED) for i in range(count)]


def retime(md, factor):
    md = bytearray(md)
    refs, _ = header_refs(md)
    (count, ofs), _, _ = refs['sequences']
    for i in range(count):
        d = struct.unpack_from('<I', md, ofs + i * 64 + SEQ_DURATION)[0]
        struct.pack_into('<I', md, ofs + i * 64 + SEQ_DURATION, int(round(d * factor)))
    (gc, go), _, _ = refs['global_loops']
    for i in range(gc):
        g = struct.unpack_from('<I', md, go + i * 4)[0]
        struct.pack_into('<I', md, go + i * 4, max(1, int(round(g * factor))) if g else 0)
    inside = embedded(md)
    for _, _, _, p, _ in walk_tracks(md):
        interp, gs, tc, to = struct.unpack_from('<HhII', md, p)
        for s in range(tc):
            if gs < 0 and s < len(inside) and not inside[s]:
                continue                          # keys in an .anim file
            n, o = struct.unpack_from('<II', md, to + s * 8)
            for k in range(n):
                v = struct.unpack_from('<I', md, o + k * 4)[0]
                struct.pack_into('<I', md, o + k * 4, int(round(v * factor)))
    return bytes(md)


def scale_float_track(md, p, factor):
    interp, gs, tc, to, vc, vo = struct.unpack_from('<HhIIII', md, p)
    for s in range(vc):
        n, o = struct.unpack_from('<II', md, vo + s * 8)
        for k in range(n):
            v = struct.unpack_from('<f', md, o + k * 4)[0]
            struct.pack_into('<f', md, o + k * 4, v * factor)


def particle_speed(md, factor):
    md = bytearray(md)
    for t, field, arg, p, _ in walk_tracks(md):
        if t != 'particle':
            continue
        if field in ('emission_speed', 'gravity'):
            scale_float_track(md, p, factor if field == 'emission_speed' else factor * factor)
        elif field == 'lifespan':
            scale_float_track(md, p, 1.0 / factor)
    return bytes(md)


def billboard_upright(md):
    md = bytearray(md)
    refs, _ = header_refs(md)
    (count, ofs), _, _ = refs['bones']
    changed = 0
    for i in range(count):
        p = ofs + i * m2.SIZES['bone'] + BONE_FLAGS
        f = struct.unpack_from('<I', md, p)[0]
        if f & BILLBOARD_ALL:
            struct.pack_into('<I', md, p, (f & ~BILLBOARD_MASK) | BILLBOARD_UPRIGHT)
            changed += 1
    return bytes(md), changed


def remap_shaders(skin, table):
    skin = bytearray(skin)
    bcount, bofs = struct.unpack_from('<II', skin, 0x24)
    changed = 0
    for i in range(bcount):
        p = bofs + i * 24 + 2
        s = struct.unpack_from('<H', skin, p)[0]
        if s in table:
            struct.pack_into('<H', skin, p, table[s])
            changed += 1
    return bytes(skin), changed
