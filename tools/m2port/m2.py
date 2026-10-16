"""
m2 -- the M2 model of the 3.3.5a client (version 264), read whole and written
again from scratch; modern models (MD21, versions 272 to 274) read into the
same form.

Every structure is described below field by field (wowdev.wiki, M2 and SKIN
pages, checked against the client's own spell models: see corpus.py and
survey.py). Reading follows every M2Array and checks it lies inside the file;
writing lays the arrays out again, so that a converted model holds nothing but
what the description says, at offsets that are its own.

A model is a dict: 'version', 'name', 'flags', the header boxes, and one list
per header array. A record is a dict of its fields; an M2Array field holds a
list (of records, numbers or tuples); an M2Track field holds
{'interpolation', 'global_sequence', 'timestamps': [[...] per sequence],
 'values': [[...] per sequence]}.
"""

import struct


class M2Error(Exception):
    pass


# --- value types --------------------------------------------------------------
# name: (struct format, size)
VALUE = {
    'u8': ('B', 1), 'i8': ('b', 1), 'u16': ('H', 2), 'i16': ('h', 2),
    'u32': ('I', 4), 'i32': ('i', 4), 'f32': ('f', 4),
    'vec2': ('2f', 8), 'vec3': ('3f', 12), 'quat': ('4f', 16),
    'compquat': ('4h', 8), 'fixed16': ('h', 2),
    'spline_vec3': ('9f', 36), 'spline_f32': ('3f', 12),
    'char': ('B', 1),
}


def vsize(t):
    return VALUE[t][1]


# --- structures ----------------------------------------------------------------
# A field is (name, kind, arg): kind 'v' a plain value of type arg, 'raw' arg
# bytes kept as they are, 'arr' an M2Array of type arg (a value type or a
# struct name), 'track' an M2Track of values arg, 'trackbase' an M2Track
# without values, 'fblock' a FakeAnimationBlock (timestamps fixed16, values arg).

STRUCTS = {
    'sequence': [
        ('id', 'v', 'u16'), ('variation', 'v', 'u16'), ('duration', 'v', 'u32'),
        ('move_speed', 'v', 'f32'), ('flags', 'v', 'u32'), ('frequency', 'v', 'i16'),
        ('padding', 'v', 'u16'), ('replay_min', 'v', 'u32'), ('replay_max', 'v', 'u32'),
        ('blend_time', 'v', 'u32'), ('bounds', 'raw', 28), ('variation_next', 'v', 'i16'),
        ('alias_next', 'v', 'u16'),
    ],
    'bone': [
        ('key_bone_id', 'v', 'i32'), ('flags', 'v', 'u32'), ('parent', 'v', 'i16'),
        ('submesh_id', 'v', 'u16'), ('crc', 'v', 'u32'),
        ('translation', 'track', 'vec3'), ('rotation', 'track', 'compquat'),
        ('scale', 'track', 'vec3'), ('pivot', 'v', 'vec3'),
    ],
    'vertex': [('raw', 'raw', 48)],
    'color': [('color', 'track', 'vec3'), ('alpha', 'track', 'fixed16')],
    'texture': [('type', 'v', 'u32'), ('flags', 'v', 'u32'), ('filename', 'arr', 'char')],
    'weight': [('weight', 'track', 'fixed16')],
    'texture_transform': [
        ('translation', 'track', 'vec3'), ('rotation', 'track', 'quat'), ('scaling', 'track', 'vec3'),
    ],
    'material': [('flags', 'v', 'u16'), ('blend', 'v', 'u16')],
    'attachment': [
        ('id', 'v', 'u32'), ('bone', 'v', 'u16'), ('unknown', 'v', 'u16'), ('position', 'v', 'vec3'),
        ('animate_attached', 'track', 'u8'),
    ],
    'event': [
        ('identifier', 'v', 'u32'), ('data', 'v', 'u32'), ('bone', 'v', 'u32'), ('position', 'v', 'vec3'),
        ('enabled', 'trackbase', None),
    ],
    'light': [
        ('type', 'v', 'u16'), ('bone', 'v', 'i16'), ('position', 'v', 'vec3'),
        ('ambient_color', 'track', 'vec3'), ('ambient_intensity', 'track', 'f32'),
        ('diffuse_color', 'track', 'vec3'), ('diffuse_intensity', 'track', 'f32'),
        ('attenuation_start', 'track', 'f32'), ('attenuation_end', 'track', 'f32'),
        ('visibility', 'track', 'u8'),
    ],
    'camera': [
        ('type', 'v', 'u32'), ('fov', 'v', 'f32'), ('far_clip', 'v', 'f32'), ('near_clip', 'v', 'f32'),
        ('positions', 'track', 'spline_vec3'), ('position_base', 'v', 'vec3'),
        ('target_positions', 'track', 'spline_vec3'), ('target_base', 'v', 'vec3'),
        ('roll', 'track', 'spline_f32'),
    ],
    'ribbon': [
        ('id', 'v', 'i32'), ('bone', 'v', 'u32'), ('position', 'v', 'vec3'),
        ('textures', 'arr', 'u16'), ('materials', 'arr', 'u16'),
        ('color', 'track', 'vec3'), ('alpha', 'track', 'fixed16'),
        ('height_above', 'track', 'f32'), ('height_below', 'track', 'f32'),
        ('edges_per_second', 'v', 'f32'), ('edge_lifetime', 'v', 'f32'), ('gravity', 'v', 'f32'),
        ('texture_rows', 'v', 'u16'), ('texture_cols', 'v', 'u16'),
        ('tex_slot', 'track', 'u16'), ('visibility', 'track', 'u8'),
        ('priority_plane', 'v', 'i16'), ('color_index', 'v', 'u8'), ('transform_lookup', 'v', 'u8'),
    ],
    'particle': [
        ('id', 'v', 'i32'), ('flags', 'v', 'u32'), ('position', 'v', 'vec3'),
        ('bone', 'v', 'u16'), ('texture', 'v', 'u16'),
        ('geometry_model', 'arr', 'char'), ('recursion_model', 'arr', 'char'),
        ('blend', 'v', 'u8'), ('emitter_type', 'v', 'u8'), ('color_index', 'v', 'u16'),
        ('particle_type', 'v', 'u8'), ('head_or_tail', 'v', 'u8'),
        ('tile_rotation', 'v', 'i16'), ('rows', 'v', 'u16'), ('cols', 'v', 'u16'),
        ('emission_speed', 'track', 'f32'), ('speed_variation', 'track', 'f32'),
        ('vertical_range', 'track', 'f32'), ('horizontal_range', 'track', 'f32'),
        ('gravity', 'track', 'f32'), ('lifespan', 'track', 'f32'), ('lifespan_vary', 'v', 'f32'),
        ('emission_rate', 'track', 'f32'), ('emission_rate_vary', 'v', 'f32'),
        ('area_length', 'track', 'f32'), ('area_width', 'track', 'f32'), ('z_source', 'track', 'f32'),
        ('color_track', 'fblock', 'vec3'), ('alpha_track', 'fblock', 'fixed16'),
        ('scale_track', 'fblock', 'vec2'), ('scale_vary', 'v', 'vec2'),
        ('head_cell', 'fblock', 'u16'), ('tail_cell', 'fblock', 'u16'),
        ('tail_length', 'v', 'f32'), ('twinkle_speed', 'v', 'f32'), ('twinkle_percent', 'v', 'f32'),
        ('twinkle_scale', 'v', 'vec2'), ('burst_multiplier', 'v', 'f32'), ('drag', 'v', 'f32'),
        ('base_spin', 'v', 'f32'), ('base_spin_vary', 'v', 'f32'), ('spin', 'v', 'f32'),
        ('spin_vary', 'v', 'f32'), ('tumble', 'raw', 24), ('wind', 'v', 'vec3'), ('wind_time', 'v', 'f32'),
        ('follow_speed1', 'v', 'f32'), ('follow_scale1', 'v', 'f32'),
        ('follow_speed2', 'v', 'f32'), ('follow_scale2', 'v', 'f32'),
        ('spline_points', 'arr', 'vec3'), ('enabled', 'track', 'u8'),
    ],
}

# Cataclysm and later: 16 bytes more at the end of a particle.
PARTICLE_MODERN_TAIL = 16

HEADER_BEFORE_SKIN = [
    ('global_loops', 'u32'), ('sequences', 'sequence'), ('sequence_lookups', 'i16'),
    ('bones', 'bone'), ('key_bone_lookup', 'i16'), ('vertices', 'vertex'),
]
HEADER_AFTER_SKIN = [
    ('colors', 'color'), ('textures', 'texture'), ('texture_weights', 'weight'),
    ('texture_transforms', 'texture_transform'), ('replaceable_texture_lookup', 'i16'),
    ('materials', 'material'), ('bone_lookup', 'i16'), ('texture_lookup', 'i16'),
    ('texture_unit_lookup', 'i16'), ('transparency_lookup', 'i16'), ('texture_transform_lookup', 'i16'),
]
HEADER_AFTER_BOX = [
    ('collision_indices', 'u16'), ('collision_positions', 'vec3'), ('collision_normals', 'vec3'),
    ('attachments', 'attachment'), ('attachment_lookup', 'i16'), ('events', 'event'),
    ('lights', 'light'), ('cameras', 'camera'), ('camera_lookup', 'i16'),
    ('ribbon_emitters', 'ribbon'), ('particle_emitters', 'particle'),
]
COMBINER_FLAG = 0x08
EMBEDDED = 0x20


def struct_size(name):
    if name in VALUE:
        return vsize(name)
    size = 0
    for _, kind, arg in STRUCTS[name]:
        size += {'v': lambda: vsize(arg), 'raw': lambda: arg, 'arr': lambda: 8, 'track': lambda: 20,
                 'trackbase': lambda: 12, 'fblock': lambda: 16}[kind]()
    return size


SIZES = {n: struct_size(n) for n in STRUCTS}
assert SIZES['particle'] == 476 and SIZES['ribbon'] == 176 and SIZES['bone'] == 88
assert SIZES['sequence'] == 64 and SIZES['camera'] == 100 and SIZES['light'] == 156


# =============================================================================
# Reading
# =============================================================================

class Reader:
    """Reads one blob, every M2Array checked against its size. `anims` gives,
    for a sequence whose keys are outside the model, the bytes of its .anim
    file: track arrays of that sequence are read from there."""

    def __init__(self, data, anims=None, particle_size=476):
        self.d = data
        self.anims = anims or {}
        self.particle_size = particle_size
        self.sequence_flags = []

    def check(self, count, ofs, size, data=None, what='array'):
        d = self.d if data is None else data
        if count and (ofs < 0 or ofs + count * size > len(d)):
            raise M2Error(f'{what}: {count} x {size} at {ofs} past the end ({len(d)})')

    def value(self, t, ofs, data=None):
        d = self.d if data is None else data
        fmt, size = VALUE[t]
        v = struct.unpack_from('<' + fmt, d, ofs)
        return v[0] if len(v) == 1 else v

    def values(self, t, count, ofs, data=None, what='values'):
        self.check(count, ofs, vsize(t), data, what)
        d = self.d if data is None else data
        fmt, size = VALUE[t]
        n = len(fmt) - (1 if fmt[0].isdigit() else 0)
        if count == 0:
            return []
        if fmt[0].isdigit():                      # tuples
            k = int(fmt[:-1])
            flat = struct.unpack_from('<%d%s' % (count * k, fmt[-1]), d, ofs)
            return [tuple(flat[i * k:(i + 1) * k]) for i in range(count)]
        return list(struct.unpack_from('<%d%s' % (count, fmt), d, ofs))

    def array(self, t, count, ofs, what):
        if t in VALUE:
            return self.values(t, count, ofs, what=what)
        size = SIZES[t] if t != 'particle' else self.particle_size
        self.check(count, ofs, size, what=what)
        return [self.record(t, ofs + i * size, f'{what}[{i}]') for i in range(count)]

    def track(self, t, ofs, what):
        interp, gs, tc, to, vc, vo = struct.unpack_from('<HhIIII', self.d, ofs)
        tr = {'interpolation': interp, 'global_sequence': gs, 'timestamps': [], 'values': []}
        self.check(tc, to, 8, what=what + '.timestamps')
        for i in range(tc):
            n, o = struct.unpack_from('<II', self.d, to + i * 8)
            src = self.source(i, gs)
            tr['timestamps'].append(self.values('u32', n, o, src, what=f'{what}.timestamps[{i}]'))
        if t is not None:
            self.check(vc, vo, 8, what=what + '.values')
            for i in range(vc):
                n, o = struct.unpack_from('<II', self.d, vo + i * 8)
                src = self.source(i, gs)
                tr['values'].append(self.values(t, n, o, src, what=f'{what}.values[{i}]'))
        return tr

    def source(self, seq, gs):
        """The bytes a track's keys of sequence `seq` are in: the model, or
        the .anim file of that sequence."""
        if gs >= 0 or seq >= len(self.sequence_flags) or self.sequence_flags[seq] & EMBEDDED:
            return None
        if seq not in self.anims:
            raise M2Error(f'sequence {seq}: keys in an .anim file not given')
        return self.anims[seq]

    def fblock(self, t, ofs, what):
        tc, to, vc, vo = struct.unpack_from('<IIII', self.d, ofs)
        return {'timestamps': self.values('fixed16', tc, to, what=what + '.timestamps'),
                'values': self.values(t, vc, vo, what=what + '.values')}

    def record(self, name, ofs, what):
        rec = {}
        p = ofs
        for field, kind, arg in STRUCTS[name]:
            if kind == 'v':
                rec[field] = self.value(arg, p)
                p += vsize(arg)
            elif kind == 'raw':
                rec[field] = bytes(self.d[p:p + arg])
                p += arg
            elif kind == 'arr':
                c, o = struct.unpack_from('<II', self.d, p)
                rec[field] = self.array(arg, c, o, f'{what}.{field}')
                p += 8
            elif kind == 'track':
                t = arg
                if name == 'particle' and field == 'gravity' and rec['flags'] & 0x800000:
                    t = 'u32'                    # compressed gravity: kept as its bits
                rec[field] = self.track(t, p, f'{what}.{field}')
                p += 20
            elif kind == 'trackbase':
                rec[field] = self.track(None, p - 0, f'{what}.{field}') if False else self.trackbase(p, f'{what}.{field}')
                p += 12
            elif kind == 'fblock':
                rec[field] = self.fblock(arg, p, f'{what}.{field}')
                p += 16
        if name == 'particle' and self.particle_size > 476:
            rec['modern_tail'] = bytes(self.d[ofs + 476:ofs + self.particle_size])
        return rec

    def trackbase(self, ofs, what):
        interp, gs, tc, to = struct.unpack_from('<HhII', self.d, ofs)
        tr = {'interpolation': interp, 'global_sequence': gs, 'timestamps': []}
        self.check(tc, to, 8, what=what)
        for i in range(tc):
            n, o = struct.unpack_from('<II', self.d, to + i * 8)
            tr['timestamps'].append(self.values('u32', n, o, self.source(i, gs), what=f'{what}[{i}]'))
        return tr


def header_arrays(flags):
    names = HEADER_BEFORE_SKIN + HEADER_AFTER_SKIN + HEADER_AFTER_BOX
    if flags & COMBINER_FLAG:
        names = names + [('texture_combiner_combos', 'u16')]
    return names


def read_md20(md, anims=None):
    """A model from its MD20 blob (any version 264 to 274)."""
    if md[:4] != b'MD20':
        raise M2Error('no MD20 magic')
    version = struct.unpack_from('<I', md, 4)[0]
    if not 264 <= version <= 274:
        raise M2Error(f'version {version}')
    modern = version >= 272
    r = Reader(md, anims, 476 + (PARTICLE_MODERN_TAIL if modern else 0))
    m = {'version': version}
    p = 8
    nc, no = struct.unpack_from('<II', md, p); p += 8
    m['name'] = bytes(r.values('char', nc, no, what='name'))
    m['flags'] = struct.unpack_from('<I', md, p)[0]; p += 4
    refs = {}
    for name, t in HEADER_BEFORE_SKIN:
        refs[name] = struct.unpack_from('<II', md, p); p += 8
    m['num_skin'] = struct.unpack_from('<I', md, p)[0]; p += 4
    for name, t in HEADER_AFTER_SKIN:
        refs[name] = struct.unpack_from('<II', md, p); p += 8
    m['boxes'] = bytes(md[p:p + 56]); p += 56
    for name, t in HEADER_AFTER_BOX:
        refs[name] = struct.unpack_from('<II', md, p); p += 8
    if m['flags'] & COMBINER_FLAG:
        refs['texture_combiner_combos'] = struct.unpack_from('<II', md, p); p += 8
    m['_header_end'] = p

    # sequences first: their flags tell where each sequence's keys live
    c, o = refs['sequences']
    m['sequences'] = r.array('sequence', c, o, 'sequences')
    r.sequence_flags = [s['flags'] for s in m['sequences']]
    for name, t in header_arrays(m['flags']):
        if name == 'sequences':
            continue
        if name == 'cameras' and modern:
            m['cameras'] = []                     # their layout changed: dropped
            continue
        c, o = refs[name]
        m[name] = r.array(t, c, o, name)
    return m


def chunks(b):
    off, out = 0, {}
    while off + 8 <= len(b):
        tag, size = struct.unpack_from('<4sI', b, off)
        out.setdefault(tag.decode('latin1'), []).append((off + 8, size))
        off += 8 + size
    return out


def read_file(b, anims=None):
    """A model from a whole .m2 file, MD20 or MD21. Returns (model, chunks):
    the chunks of a modern file (TXID, SFID, AFID...) as raw bytes."""
    if b[:4] == b'MD21':
        ch = chunks(b)
        o, s = ch['MD21'][0]
        extra = {k: b[v[0][0]:v[0][0] + v[0][1]] for k, v in ch.items() if k != 'MD21'}
        return read_md20(b[o:o + s], anims), extra
    return read_md20(b, anims), {}


# =============================================================================
# Writing (version 264)
# =============================================================================

class Writer:
    def __init__(self):
        self.d = bytearray()

    def align(self, n=16):
        while len(self.d) % n:
            self.d.append(0)

    def put(self, data, align=16):
        if not data:
            return 0
        self.align(align)
        ofs = len(self.d)
        self.d += data
        return ofs

    def pack_values(self, t, values):
        fmt, size = VALUE[t]
        if not values:
            return b''
        if fmt[0].isdigit():
            k = int(fmt[:-1])
            flat = [x for v in values for x in v]
            return struct.pack('<%d%s' % (len(values) * k, fmt[-1]), *flat)
        return struct.pack('<%d%s' % (len(values), fmt), *values)

    def array(self, t, items):
        """Writes the items (and what they refer to); returns (count, offset)."""
        if not items:
            return 0, 0
        if t in VALUE:
            return len(items), self.put(self.pack_values(t, items), 4 if vsize(t) < 4 else 16)
        size = SIZES[t]
        ofs = self.put(bytes(size * len(items)))
        for i, rec in enumerate(items):
            self.d[ofs + i * size:ofs + (i + 1) * size] = self.record(t, rec)
        return len(items), ofs

    def nested(self, t, lists):
        """M2Array<M2Array<T>>: the inner arrays, then the outer one."""
        if not lists:
            return 0, 0
        refs = [self.array(t, vals) if vals else (0, 0) for vals in lists]
        ofs = self.put(struct.pack('<%dI' % (2 * len(refs)), *[x for r in refs for x in r]))
        return len(refs), ofs

    def track(self, t, tr):
        tc, to = self.nested('u32', tr['timestamps'])
        vc, vo = self.nested(t, tr['values']) if t else (0, 0)
        return struct.pack('<HhIIII', tr['interpolation'], tr['global_sequence'], tc, to, vc, vo)

    def record(self, name, rec):
        out = bytearray()
        for field, kind, arg in STRUCTS[name]:
            v = rec[field]
            if kind == 'v':
                fmt = VALUE[arg][0]
                out += struct.pack('<' + fmt, *(v if isinstance(v, tuple) else (v,)))
            elif kind == 'raw':
                out += v
            elif kind == 'arr':
                out += struct.pack('<II', *self.array(arg, v))
            elif kind == 'track':
                out += self.track(arg, v)
            elif kind == 'trackbase':
                tc, to = self.nested('u32', v['timestamps'])
                out += struct.pack('<HhII', v['interpolation'], v['global_sequence'], tc, to)
            elif kind == 'fblock':
                tc, to = self.array('fixed16', v['timestamps'])
                vc, vo = self.array(arg, v['values'])
                out += struct.pack('<IIII', tc, to, vc, vo)
        return bytes(out)


def write(m):
    """The model as a version 264 file."""
    w = Writer()
    names = header_arrays(m['flags'])
    header_size = 8 + 8 + 4 + 8 * len(HEADER_BEFORE_SKIN) + 4 + 8 * len(HEADER_AFTER_SKIN) + 56 \
        + 8 * len(HEADER_AFTER_BOX) + (8 if m['flags'] & COMBINER_FLAG else 0)
    w.d += bytes(header_size)
    refs = {}
    name = m['name'] if m['name'].endswith(b'\0') else m['name'] + b'\0'
    refs['name'] = w.array('char', list(name))
    for n, t in names:
        refs[n] = w.array(t, m.get(n, []))
    h = bytearray()
    h += b'MD20' + struct.pack('<I', 264)
    h += struct.pack('<II', *refs['name']) + struct.pack('<I', m['flags'])
    for n, _ in HEADER_BEFORE_SKIN:
        h += struct.pack('<II', *refs[n])
    h += struct.pack('<I', m['num_skin'])
    for n, _ in HEADER_AFTER_SKIN:
        h += struct.pack('<II', *refs[n])
    h += m['boxes']
    for n, _ in HEADER_AFTER_BOX:
        h += struct.pack('<II', *refs[n])
    if m['flags'] & COMBINER_FLAG:
        h += struct.pack('<II', *refs['texture_combiner_combos'])
    assert len(h) == header_size
    w.d[:header_size] = h
    return bytes(w.d)


# =============================================================================
# Skins
# =============================================================================

SUBMESH = [('id', 'u16'), ('level', 'u16'), ('vertex_start', 'u16'), ('vertex_count', 'u16'),
           ('index_start', 'u16'), ('index_count', 'u16'), ('bone_count', 'u16'), ('bone_combo', 'u16'),
           ('bone_influences', 'u16'), ('center_bone', 'u16'), ('center', 'vec3'), ('sort_center', 'vec3'),
           ('sort_radius', 'f32')]
BATCH = [('flags', 'u8'), ('priority', 'i8'), ('shader', 'u16'), ('submesh', 'u16'), ('geoset', 'u16'),
         ('color', 'i16'), ('material', 'u16'), ('layer', 'u16'), ('texture_count', 'u16'),
         ('texture_combo', 'u16'), ('coord_combo', 'u16'), ('weight_combo', 'u16'), ('transform_combo', 'u16')]


def _rec(layout, d, ofs):
    rec = {}
    for n, t in layout:
        rec[n] = struct.unpack_from('<' + VALUE[t][0], d, ofs)
        rec[n] = rec[n][0] if len(rec[n]) == 1 else rec[n]
        ofs += vsize(t)
    return rec


def _pack(layout, rec):
    out = b''
    for n, t in layout:
        v = rec[n]
        out += struct.pack('<' + VALUE[t][0], *(v if isinstance(v, tuple) else (v,)))
    return out


def read_skin(d):
    if d[:4] != b'SKIN':
        raise M2Error('no SKIN magic')
    s = {}
    refs = [struct.unpack_from('<II', d, 4 + 8 * i) for i in range(5)]
    for (c, o), size in zip(refs, (2, 2, 4, 48, 24)):
        if c and o + c * size > len(d):
            raise M2Error('skin array past the end')
    s['vertices'] = list(struct.unpack_from('<%dH' % refs[0][0], d, refs[0][1])) if refs[0][0] else []
    s['indices'] = list(struct.unpack_from('<%dH' % refs[1][0], d, refs[1][1])) if refs[1][0] else []
    s['bones'] = [tuple(d[refs[2][1] + 4 * i:refs[2][1] + 4 * i + 4]) for i in range(refs[2][0])]
    s['submeshes'] = [_rec(SUBMESH, d, refs[3][1] + 48 * i) for i in range(refs[3][0])]
    s['batches'] = [_rec(BATCH, d, refs[4][1] + 24 * i) for i in range(refs[4][0])]
    s['bone_count_max'] = struct.unpack_from('<I', d, 44)[0]
    return s


def write_skin(s):
    w = Writer()
    w.d += bytes(48)
    refs = [
        (len(s['vertices']), w.put(struct.pack('<%dH' % len(s['vertices']), *s['vertices']), 4)),
        (len(s['indices']), w.put(struct.pack('<%dH' % len(s['indices']), *s['indices']), 4)),
        (len(s['bones']), w.put(bytes(x for b in s['bones'] for x in b), 4)),
        (len(s['submeshes']), w.put(b''.join(_pack(SUBMESH, r) for r in s['submeshes']), 4)),
        (len(s['batches']), w.put(b''.join(_pack(BATCH, r) for r in s['batches']), 4)),
    ]
    refs = [(c, o if c else 0) for c, o in refs]
    w.d[:48] = b'SKIN' + b''.join(struct.pack('<II', *r) for r in refs) + struct.pack('<I', s['bone_count_max'])
    return bytes(w.d)
