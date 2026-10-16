"""
survey -- reads every model of a folder with m2.py, writes it again and reads
it back (the round trip must give the same model), and gathers what values
the models use: the domains a converted model must stay within.

    python survey.py <folder> [<domains.json to write>]
"""

import collections
import glob
import json
import os
import sys

import m2

BITS = lambda v: [1 << b for b in range(32) if v >> b & 1]  # noqa: E731


def strip(m):
    return {k: v for k, v in m.items() if not k.startswith('_')}


def gather(dom, m, skin):
    def add(key, v):
        dom[key][v] += 1

    add('header_flag_bits', 0) if not m['flags'] else [add('header_flag_bits', b) for b in BITS(m['flags'])]
    for mat in m['materials']:
        add('material_blend', mat['blend'])
        for b in BITS(mat['flags']):
            add('material_flag_bits', b)
    for s in m['sequences']:
        add('sequence_id', s['id'])
        for b in BITS(s['flags']):
            add('sequence_flag_bits', b)
    for p in m['particle_emitters']:
        add('particle_blend', p['blend'])
        add('particle_emitter_type', p['emitter_type'])
        add('particle_type', p['particle_type'])
        add('particle_head_or_tail', p['head_or_tail'])
        for b in BITS(p['flags']):
            add('particle_flag_bits', b)
        rates = [x for vals in p['emission_rate']['values'] for x in vals]
        lifes = [x for vals in p['lifespan']['values'] for x in vals]
        if rates and lifes:
            add('particle_load_bucket', min(int(max(rates) * max(lifes)) // 100 * 100, 5000))
    for r in m['ribbon_emitters']:
        add('ribbon_rows_cols', (r['texture_rows'], r['texture_cols']))
    for t in m['textures']:
        add('texture_type', t['type'])
        add('texture_flags', t['flags'])
    for tr_owner in m['bones']:
        for f in ('translation', 'rotation', 'scale'):
            add('bone_interpolation', tr_owner[f]['interpolation'])
    if skin:
        for b in skin['batches']:
            add('batch_shader', b['shader'])
            add('batch_texture_count', b['texture_count'])
            add('batch_flags', b['flags'])
            add('batch_shader_with_combiners' if m['flags'] & 8 else 'batch_shader_without', (b['shader'], b['texture_count']))
    add('texture_unit_lookup_values', tuple(m['texture_unit_lookup']))
    if m['flags'] & 8:
        add('combiner_combos', tuple(m['texture_combiner_combos']))
    add('global_loop_zero', 0 in m['global_loops'])


def main(folder, out=None):
    dom = collections.defaultdict(collections.Counter)
    ok = bad = trip = 0
    faults = collections.Counter()
    for path in sorted(glob.glob(os.path.join(folder, '*.m2'))):
        b = open(path, 'rb').read()
        try:
            model, _ = m2.read_file(b)
        except m2.M2Error as e:
            bad += 1
            faults[str(e).split(':')[0][:60]] += 1
            continue
        except Exception as e:                    # noqa: BLE001
            bad += 1
            faults[type(e).__name__ + ' ' + str(e)[:50]] += 1
            continue
        ok += 1
        skin = None
        sp = os.path.splitext(path)[0] + '00.skin'
        if os.path.exists(sp):
            try:
                skin = m2.read_skin(open(sp, 'rb').read())
                assert m2.read_skin(m2.write_skin(skin)) == skin
            except (m2.M2Error, AssertionError):
                faults['skin round trip'] += 1
        if model['version'] == 264:
            again = m2.read_md20(m2.write(model))
            if strip(again) != strip(model):
                trip += 1
                diff = [k for k in model if not k.startswith('_') and again.get(k) != model.get(k)]
                faults['round trip differs: ' + ','.join(diff[:3])] += 1
        gather(dom, model, skin)
    print(f'read {ok}, unreadable {bad}, round trip differences {trip}')
    for k, v in faults.most_common(12):
        print(f'  {v:5}  {k}')
    for key in sorted(dom):
        items = dom[key].most_common(14)
        print(f'{key}: ' + ', '.join(f'{k}:{n}' for k, n in items) + (' ...' if len(dom[key]) > 14 else ''))
    if out:
        json.dump({k: {str(x): n for x, n in v.items()} for k, v in dom.items()}, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:3])
