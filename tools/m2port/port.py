"""
port -- a modern spell model (MD21, versions 272 to 274, as export.py or
wow.export export it in RAW) rebuilt for the 3.3.5a client (version 264).

    python port.py <model.m2> <output folder> <new name> [<game folder>]

The model is read whole (m2.py), changed field by field, then written again
from scratch: nothing of the modern layout survives but what 3.3.5 reads. Every
value is brought into the domain the client's own spell models use (see
survey.py on the corpus of corpus.py); validate.py then refuses any model that
still holds something else.

THE SHADERS. A modern batch names its shader by an ID that 3.3.5 does not know:
- below 0x8000: the blend of each texture stage in bits ((id >> 4) & 7, id & 7),
  0x4000 when the second stage reads the second UV set, 0x80 / 0x08 when a
  stage is an environment map. Two stages become a texture combiner combo of
  3.3.5 (header flag 0x08, the batch's shader its index), exactly what the
  client's own spell models do; one stage keeps one texture.
- 0x8000 and up: one of the modern "effects". Those of two passes are split
  into two batches, the second drawn over the first; the others keep their
  first texture. The table is MultiConverter's (MultiConverterLib/SkinFix.cs),
  the converter the WotLK modding community has used for years.

THE REST. Texture paths for FileDataIDs; blend modes past 6 to add; flags of
materials, batches, particles, sequences and the header masked to the bits
3.3.5 uses; global loops of 0 ms to 1; particle emitters without geometry
models, with one texture, a 3.3.5 emitter type and an emission rate brought
down to what the client sustains (rate x lifespan); cameras dropped (their
layout changed); keys of every sequence inside the model.
"""

import json
import os
import shutil
import struct
import sys

import m2

# What 3.3.5's own spell models use (survey.py on the corpus).
PARTICLE_FLAGS = 0x000FF7FF & ~0x800          # bits 0x1 to 0x80000, without 0x800
MATERIAL_FLAGS = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x40 | 0x100
SEQUENCE_FLAGS = 0x1 | 0x2 | 0x20 | 0x40 | 0x80
HEADER_FLAGS = 0x1 | 0x2 | 0x4 | 0x10      # 0x08 is set again when combos are written
BATCH_FLAGS = 0x1F
PARTICLE_BLENDS = {0, 1, 2, 4, 5}
EMITTER_TYPES = {1, 2, 3}
# particles alive at once per emitter (emission rate x lifespan): the client's
# own spells stay under 1,000, a few reach 3,000
PARTICLE_LOAD = 800
MODEL_LOAD = 2000
MAX_ANIM_ID = 505
BONE_PALETTES = (21, 53, 64, 256)          # boneCountMax values of the client's skins


class Fault(Exception):
    pass


# =============================================================================
# Shaders: modern batch -> batches of 3.3.5 with texture combiner combos
# =============================================================================

class Combos:
    """The texture combiner combos and the texture unit lookup being built."""

    def __init__(self):
        self.combos = []           # pairs of stage blends
        self.units = []            # UV set of each stage (-1: environment map)

    def pair(self, b1, b2):
        for n in range(0, len(self.combos), 2):
            if self.combos[n] == b1 and self.combos[n + 1] == b2:
                return n
        self.combos += [b1, b2]
        return len(self.combos) - 2

    def unit(self, *stages):
        """The index of a run of UV sets in the lookup, added when missing."""
        k = len(stages)
        for n in range(len(self.units) - k + 1):
            if tuple(self.units[n:n + k]) == stages:
                return n
        # extend a tail that already starts the run
        for keep in range(min(k - 1, len(self.units)), 0, -1):
            if tuple(self.units[-keep:]) == stages[:keep]:
                self.units += list(stages[keep:])
                return len(self.units) - k
        self.units += list(stages)
        return len(self.units) - k


def convert_batches(skin, model, combos):
    """The skin's batches in 3.3.5 terms (after SkinFix.cs)."""
    n_transparency = len(model['transparency_lookup'])
    bad_sections = set()
    for i, s in enumerate(skin['submeshes']):
        if s['level'] > 0:                       # past 65,535 indices: dropped
            for k in ('level', 'vertex_start', 'vertex_count', 'index_start', 'index_count',
                      'bone_count', 'bone_combo', 'bone_influences'):
                s[k] = 0
            bad_sections.add(i)
        elif s['bone_influences'] & 0xFF == 0:
            s['bone_influences'] = 1
        s['bone_influences'] &= 0xFF

    out = []
    for b in skin['batches']:
        b = dict(b)
        shader, count = b['shader'], b['texture_count']
        b['flags'] &= BATCH_FLAGS
        if b['submesh'] in bad_sections:
            continue
        second = None

        if shader >= 0x8000:
            low = shader & 0xFF
            if low in (0, 3, 9, 17, 24, 2):
                # two passes: the first texture, then the second one over it
                b1, b2 = (1, 3) if low == 2 else (1, 4)
                second = dict(b)
                second['texture_count'] = 1
                second['material'] = min(b['material'] + 1, len(model['materials']) - 1)
                second['layer'] = 1
                idx = combos.pair(b1, b2)
                unit = combos.unit(0, -1)
                b.update(shader=idx, texture_count=2, coord_combo=unit)
                second.update(shader=idx, coord_combo=unit)
            elif low in (1, 15):
                second = dict(b)
                b['texture_count'] = 1
                second['texture_count'] = 1
                second['material'] = min(b['material'] + 1, len(model['materials']) - 1)
                second['layer'] = 1
                second['texture_combo'] = b['texture_combo'] + 1
                if b['weight_combo'] + 1 < n_transparency:
                    second['weight_combo'] = b['weight_combo'] + 1
                unit = combos.unit(0, -1 if shader == 0x8001 else 1)
                b.update(shader=0, coord_combo=unit)
                second.update(shader=0, coord_combo=unit + 1)
            elif low == 21:
                shader, count = 0x4011, 2
            elif low in (5, 8, 10, 12, 16, 23):
                shader, count = 0, 1
            else:
                shader, count = 0x0010, 1

        if shader < 0x8000:
            b1, b2 = (shader >> 4) & 7, shader & 7
            two = count > 1 and shader & 0x4000 and b1 and b2
            if two:
                b['shader'] = combos.pair(b1, b2)
                env1 = bool(shader & 0x80)
                u0 = -1 if env1 else 0
                u1 = -1 if shader & 0x8 else (0 if env1 else 1)
                b['coord_combo'] = combos.unit(u0, u1)
                b['texture_count'] = 2
            else:
                b['shader'] = 0
                b['texture_count'] = 1
                b['coord_combo'] = combos.unit(-1 if shader & 0x80 else 0)

        out.append(b)
        if second is not None:
            out.append(second)
    skin['batches'] = out


# =============================================================================
# The model
# =============================================================================

def track_values(tr):
    return [x for vals in tr['values'] for x in vals]


def scale_track(tr, k):
    tr['values'] = [[v * k for v in vals] for vals in tr['values']]


def emitter_load(p):
    rates, lifes = track_values(p['emission_rate']), track_values(p['lifespan'])
    return max(rates) * max(max(lifes), 0.01) if rates and lifes else 0.0


def model_load(model):
    return sum(emitter_load(p) for p in model['particle_emitters'])


def convert_particle(p):
    flags = p['flags']
    if flags & 0x800000:                         # compressed gravity -> scalar pulling down
        for vals in p['gravity']['values']:
            for i, v in enumerate(vals):
                x, y, z = struct.unpack('<bbh', struct.pack('<I', v))
                dx, dy = x / 128.0, y / 128.0
                dz = max(0.0, 1.0 - dx * dx - dy * dy) ** 0.5
                mag = z * 0.04238648
                if mag < 0:
                    dz, mag = -dz, -mag
                vals[i] = -(dz * mag)
    if flags & 0x10000000:                       # three textures packed: the first
        p['texture'] &= 0x1F
    p['flags'] = flags & PARTICLE_FLAGS
    if p['blend'] not in PARTICLE_BLENDS:
        p['blend'] = 4
    if p['emitter_type'] not in EMITTER_TYPES:
        p['emitter_type'] = 1
    p['particle_type'] = 0
    p['head_or_tail'] = 0
    p['geometry_model'] = []
    p['recursion_model'] = []
    p.pop('modern_tail', None)
    rates, lifes = track_values(p['emission_rate']), track_values(p['lifespan'])
    if rates and lifes:
        load = max(rates) * max(max(lifes), 0.01)
        if load > PARTICLE_LOAD:
            scale_track(p['emission_rate'], PARTICLE_LOAD / load)


def external_anims(b, manifest, srcdir):
    """For each sequence whose keys live outside the model, the bytes of its
    .anim file (the AFM2 chunk of a modern one): {sequence index: bytes}. The
    offsets of those keys are relative to that data, as in 3.3.5 .anim files.
    Wrath and later sequences without flag 0x20 are matched by (id, variation)."""
    files = {(a['animID'], a['subAnimID']): os.path.join(srcdir, a['file']) for a in manifest.get('anims', [])}
    if not files:
        return {}
    model_chunks = m2.chunks(b)
    o, s = model_chunks['MD21'][0]
    md = b[o:o + s]
    count, ofs = struct.unpack_from('<II', md, 8 + 8 + 4 + 8)        # sequences
    out = {}
    for i in range(count):
        sid, variation = struct.unpack_from('<HH', md, ofs + i * m2.SIZES['sequence'])
        flags = struct.unpack_from('<I', md, ofs + i * m2.SIZES['sequence'] + 12)[0]
        if flags & m2.EMBEDDED or (sid, variation) not in files:
            continue
        data = open(files[(sid, variation)], 'rb').read()
        if data[:4] in (b'AFM2', b'AFSA', b'AFSB'):
            ch = m2.chunks(data)
            if 'AFM2' not in ch:
                raise Fault(f'animation {sid}-{variation}: no AFM2 chunk')
            co, cs = ch['AFM2'][0]
            data = data[co:co + cs]
        out[i] = data
    return out


def port(src, outdir, newname, gamedir='Spells\\LimitBreak'):
    b = open(src, 'rb').read()
    manifest = json.load(open(os.path.splitext(src)[0] + '.manifest.json', encoding='utf-8'))
    srcdir = os.path.dirname(src)
    model, chunks = m2.read_file(b, external_anims(b, manifest, srcdir))
    if not 272 <= model['version'] <= 274:
        raise Fault(f"version {model['version']}: 272 to 274 handled")
    # every sequence's keys now live in the model: the writer puts them there
    for s in model['sequences']:
        s['flags'] |= m2.EMBEDDED
    tex_files = {t['fileDataID']: os.path.normpath(os.path.join(srcdir, t['file'])) for t in manifest['textures']}
    txid = list(struct.unpack('<%dI' % (len(chunks.get('TXID', b'')) // 4), chunks.get('TXID', b'')))
    notes = []
    os.makedirs(outdir, exist_ok=True)

    model['name'] = newname.encode('ascii')
    model['num_skin'] = 1
    model['flags'] &= HEADER_FLAGS

    for s in model['sequences']:
        s['flags'] &= SEQUENCE_FLAGS
        s['blend_time'] &= 0xFFFF
        if s['id'] > MAX_ANIM_ID:
            s['id'] = 0
    model['global_loops'] = [g or 1 for g in model['global_loops']]

    for i, t in enumerate(model['textures']):
        if t['type'] != 0:
            continue
        fid = txid[i] if i < len(txid) else 0
        source = tex_files.get(fid)
        if not source or not os.path.exists(source):
            raise Fault(f'texture {i} (FileDataID {fid}) missing from the export')
        base = os.path.splitext(os.path.basename(source))[0].lower()
        target = base + '.blp' if base.endswith(str(fid)) else f'{base}_{fid}.blp'
        shutil.copyfile(source, os.path.join(outdir, target))
        t['filename'] = list((gamedir + '\\' + target).encode('ascii') + b'\0')
        t['flags'] &= 0x3

    for mat in model['materials']:
        if mat['blend'] > 6:
            mat['blend'], mat['flags'] = 4, mat['flags'] | 0x5
        if mat['blend'] == 3:
            mat['blend'] = 4
        mat['flags'] &= MATERIAL_FLAGS

    for p in model['particle_emitters']:
        convert_particle(p)
    # the whole model too: 99 % of the client's own spells stay under 2,000
    total = model_load(model)
    if total > MODEL_LOAD:
        for p in model['particle_emitters']:
            scale_track(p['emission_rate'], MODEL_LOAD / total)
    for r in model['ribbon_emitters']:
        r['texture_rows'] = max(r['texture_rows'], 1)
        r['texture_cols'] = max(r['texture_cols'], 1)
    model['cameras'] = []
    model['camera_lookup'] = []

    skin = m2.read_skin(open(os.path.join(srcdir, manifest['skins'][0]['file']), 'rb').read())
    combos = Combos()
    convert_batches(skin, model, combos)
    if combos.combos:
        if combos.combos[0] != 1:                # one-texture batches use the first combo
            for bt in skin['batches']:
                if bt['texture_count'] == 2:
                    bt['shader'] += 2
            combos.combos = [1, 0] + combos.combos
        model['flags'] |= m2.COMBINER_FLAG
        model['texture_combiner_combos'] = combos.combos
    model['texture_unit_lookup'] = combos.units or [0]
    # a batch reads one entry per texture from each lookup: modern models stop
    # some tables short of a two-texture batch's second entry, which the old
    # client would read past the end -- that entry is added, the same as the first
    for table, field, empty in (('transparency_lookup', 'weight_combo', 0),
                                ('texture_transform_lookup', 'transform_combo', -1),
                                ('texture_lookup', 'texture_combo', 0)):
        lookup = model[table]
        for bt in skin['batches']:
            first = lookup[bt[field]] if bt[field] < len(lookup) else empty
            while len(lookup) < bt[field] + bt['texture_count']:
                lookup.append(first)
    # the client's own skins use only these sizes of bone palette: the smallest
    # that holds the submesh with most bones (138 bones written as is crashed it)
    most = max([s['bone_count'] for s in skin['submeshes']] or [0])
    skin['bone_count_max'] = next((v for v in BONE_PALETTES if v >= most), None)
    if skin['bone_count_max'] is None:
        raise Fault(f'a submesh uses {most} bones, past {BONE_PALETTES[-1]}')

    open(os.path.join(outdir, newname + '.m2'), 'wb').write(m2.write(model))
    open(os.path.join(outdir, newname + '00.skin'), 'wb').write(m2.write_skin(skin))
    return notes


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    try:
        for n in port(*sys.argv[1:5]):
            print('note:', n)
    except (Fault, m2.M2Error) as e:
        print('FAILED:', e)
        sys.exit(2)
    print('ok')
