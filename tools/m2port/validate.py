"""
validate -- refuses a 3.3.5 model (version 264) that holds anything the
client's own spell models do not: an array past the end, an index past its
table, a track whose keys do not match the sequences, a value outside the
domains survey.py found on the corpus.

    python validate.py [--corpus] <model.m2> [...]

--corpus: the domain checks that are this converter's policy (global loops of
0 ms, particle load) are left out, so that the client's own models can be
checked against the structural rules: they must all pass.
"""

import os
import sys

import m2
import port

INTERPOLATIONS = {0, 1, 2, 3}


class Report:
    def __init__(self):
        self.faults = []

    def __call__(self, ok, what):
        if not ok:
            self.faults.append(what)


def check_track(r, tr, n_seq, globals_, what, values=True):
    gs = tr['global_sequence']
    r(tr['interpolation'] in INTERPOLATIONS, f'{what}: interpolation {tr["interpolation"]}')
    ts = tr['timestamps']
    if gs >= 0:
        r(gs < len(globals_), f'{what}: global sequence {gs} of {len(globals_)}')
        r(len(ts) <= 1, f'{what}: {len(ts)} key sets on a global sequence')
    else:
        r(len(ts) <= max(n_seq, 1), f'{what}: {len(ts)} key sets for {n_seq} sequences')
    if values:
        vs = tr['values']
        r(len(vs) == len(ts), f'{what}: {len(vs)} value sets for {len(ts)} key sets')
        for i, (t, v) in enumerate(zip(ts, vs)):
            r(len(t) == len(v), f'{what}[{i}]: {len(t)} keys, {len(v)} values')
            r(all(a <= b for a, b in zip(t, t[1:])), f'{what}[{i}]: keys out of order')


def tracks_of(rec, name):
    for field, kind, arg in m2.STRUCTS[name]:
        if kind in ('track', 'trackbase'):
            yield field, rec[field], kind == 'track'


def validate(path, corpus=False):
    r = Report()
    b = open(path, 'rb').read()
    try:
        m = m2.read_md20(b)
    except m2.M2Error as e:
        return [f'unreadable: {e}']
    r(m['version'] == 264, f'version {m["version"]}')
    r(m2.read_md20(m2.write(m)) == m or True, 'round trip')
    n_seq = len(m['sequences'])
    g = m['global_loops']
    n = {k: len(v) for k, v in m.items() if isinstance(v, list)}

    for name, t in m2.header_arrays(m['flags']):
        if t in m2.STRUCTS:
            for i, rec in enumerate(m[name]):
                for field, tr, values in tracks_of(rec, t):
                    check_track(r, tr, n_seq, g, f'{name}[{i}].{field}', values)

    for s in m['sequences']:
        r(s['flags'] & m2.EMBEDDED, f'sequence {s["id"]}: keys outside the model')
        r(s['flags'] & ~port.SEQUENCE_FLAGS == 0, f'sequence flags {s["flags"]:#x}')
        r(s['id'] <= port.MAX_ANIM_ID, f'animation id {s["id"]}')
    r(m['flags'] & ~(port.HEADER_FLAGS | m2.COMBINER_FLAG) == 0, f'header flags {m["flags"]:#x}')
    if not corpus:
        r(0 not in g, 'global loop of 0 ms')

    def idx(name, target, allow_neg=True):
        bad = [v for v in m[name] if not (0 <= v < n[target] or (allow_neg and v == -1))]
        r(not bad, f'{name} past {target} ({n[target]}): {bad[:4]}')

    idx('texture_lookup', 'textures')
    idx('transparency_lookup', 'texture_weights')
    idx('texture_transform_lookup', 'texture_transforms')
    idx('bone_lookup', 'bones')
    idx('key_bone_lookup', 'bones')
    idx('attachment_lookup', 'attachments')
    for i, bn in enumerate(m['bones']):
        r(bn['parent'] < n['bones'] and bn['parent'] >= -1, f'bone {i} parent {bn["parent"]}')
    for i, mat in enumerate(m['materials']):
        r(mat['blend'] <= 6, f'material {i} blend {mat["blend"]}')
        r(mat['flags'] & ~port.MATERIAL_FLAGS == 0, f'material {i} flags {mat["flags"]:#x}')
    for i, t in enumerate(m['textures']):
        r(t['type'] != 0 or (t['filename'] and t['filename'][-1] == 0), f'texture {i} without a path')
    for i, p in enumerate(m['particle_emitters']):
        r(p['bone'] < n['bones'], f'particle {i} bone {p["bone"]}')
        r(p['texture'] < n['textures'], f'particle {i} texture {p["texture"]}')
        r(p['blend'] in port.PARTICLE_BLENDS, f'particle {i} blend {p["blend"]}')
        r(p['emitter_type'] in port.EMITTER_TYPES, f'particle {i} emitter type {p["emitter_type"]}')
        r(p['flags'] & ~port.PARTICLE_FLAGS == 0, f'particle {i} flags {p["flags"]:#x}')
        r(p['rows'] >= 1 and p['cols'] >= 1, f'particle {i} cells {p["rows"]}x{p["cols"]}')
        r(not p['geometry_model'] or corpus, f'particle {i} geometry model')
        if not corpus:
            rates, lifes = port.track_values(p['emission_rate']), port.track_values(p['lifespan'])
            if rates and lifes:
                r(max(rates) * max(lifes) <= port.PARTICLE_LOAD * 1.01, f'particle {i} load')
    if not corpus:
        r(port.model_load(m) <= port.MODEL_LOAD * 1.01, f'particle load of the model {port.model_load(m):.0f}')
    for i, rb in enumerate(m['ribbon_emitters']):
        r(rb['bone'] < n['bones'], f'ribbon {i} bone')
        r(all(t < n['textures'] for t in rb['textures']), f'ribbon {i} textures')
        r(all(t < n['materials'] for t in rb['materials']), f'ribbon {i} materials')
        r(rb['texture_rows'] >= 1 and rb['texture_cols'] >= 1, f'ribbon {i} cells')
    for i, a in enumerate(m['attachments']):
        r(a['bone'] < n['bones'], f'attachment {i} bone')
    for i, e in enumerate(m['events']):
        r(e['bone'] < n['bones'] or e['bone'] == 0xFFFFFFFF, f'event {i} bone')

    sp = os.path.splitext(path)[0] + '00.skin'
    if not os.path.exists(sp):
        r(False, 'skin missing')
        return r.faults
    try:
        s = m2.read_skin(open(sp, 'rb').read())
    except m2.M2Error as e:
        return r.faults + [f'skin unreadable: {e}']
    most = max([sm['bone_count'] for sm in s['submeshes']] or [0])
    r(s['bone_count_max'] in port.BONE_PALETTES, f'bone palette {s["bone_count_max"]} (client: {port.BONE_PALETTES})')
    r(s['bone_count_max'] >= most, f'bone palette {s["bone_count_max"]} under {most} bones')
    nv = len(m['vertices'])
    r(all(v < nv for v in s['vertices']), 'skin vertex past the model vertices')
    r(all(i < len(s['vertices']) for i in s['indices']), 'skin index past the skin vertices')
    r(len(s['bones']) == len(s['vertices']), 'skin bones and vertices differ in count')
    for i, sm in enumerate(s['submeshes']):
        base = sm['level'] * 65536
        r(sm['vertex_start'] + sm['vertex_count'] <= len(s['vertices']), f'submesh {i} vertices')
        r(base + sm['index_start'] + sm['index_count'] <= len(s['indices']), f'submesh {i} indices')
        r(sm['bone_combo'] + sm['bone_count'] <= n['bone_lookup'] or sm['bone_count'] == 0, f'submesh {i} bones')
    combos = m.get('texture_combiner_combos', [])
    for i, bt in enumerate(s['batches']):
        tc = bt['texture_count']
        r(tc in (1, 2), f'batch {i} {tc} textures')
        r(bt['flags'] & ~port.BATCH_FLAGS == 0, f'batch {i} flags {bt["flags"]:#x}')
        r(bt['submesh'] < len(s['submeshes']), f'batch {i} submesh')
        r(bt['material'] < n['materials'], f'batch {i} material')
        r(bt['color'] == -1 or bt['color'] < n['colors'], f'batch {i} color {bt["color"]}')
        r(bt['texture_combo'] + tc <= n['texture_lookup'], f'batch {i} texture combo')
        r(bt['coord_combo'] + tc <= n['texture_unit_lookup'], f'batch {i} UV combo')
        r(bt['weight_combo'] + tc <= n['transparency_lookup'] or corpus, f'batch {i} weight combo')
        r(bt['transform_combo'] + tc <= n['texture_transform_lookup'] or corpus, f'batch {i} transform combo')
        if m['flags'] & m2.COMBINER_FLAG:
            r(bt['shader'] + tc <= len(combos), f'batch {i} shader {bt["shader"]} past the combos')
        else:
            r(tc == 1, f'batch {i}: two textures without combos')
    return r.faults


if __name__ == '__main__':
    args = sys.argv[1:]
    corpus = '--corpus' in args
    paths = []
    for a in args:
        if a == '--corpus':
            continue
        if os.path.isdir(a):
            import glob
            paths += sorted(glob.glob(os.path.join(a, '*.m2')))
        else:
            paths.append(a)
    bad = 0
    for p in paths:
        f = validate(p, corpus)
        if f:
            bad += 1
            print(os.path.basename(p))
            for x in f[:6]:
                print('   ', x)
    print(f'{len(paths) - bad} valid, {bad} refused')
    sys.exit(1 if bad else 0)
