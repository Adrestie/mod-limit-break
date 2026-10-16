"""
check -- what in a converted model (3.3.5, version 264) would make the old
client read out of bounds or divide by zero: indices of the skin batches and
of the lookups past their tables, zero-length global loops, particles naming a
texture the model lacks.

    python check.py <model.m2> [...]
"""

import os
import struct
import sys

from m2port import array, header_layout


def u16s(md, count, ofs, signed=True):
    return list(struct.unpack_from('<%d%s' % (count, 'h' if signed else 'H'), md, ofs)) if count else []


def check(path):
    md = open(path, 'rb').read()
    f, _ = header_layout(md)
    faults = []
    n = {k: array(md, f, k)[0] for k in f if k not in ('name', 'flags', 'num_skin') and isinstance(f[k], int)}

    gc, go = array(md, f, 'global_loops')
    if gc and 0 in struct.unpack_from('<%dI' % gc, md, go):
        faults.append('global loop of 0 ms')

    def lookup(name, target):
        c, o = array(md, f, name)
        bad = [v for v in u16s(md, c, o) if v != -1 and not 0 <= v < n[target]]
        if bad:
            faults.append(f'{name} points past {target} ({n[target]}): {bad[:5]}')

    lookup('texture_lookup', 'textures')
    lookup('transparency_lookup', 'texture_weights')
    lookup('texture_transform_lookup', 'texture_transforms')
    lookup('bone_lookup', 'bones')

    pc, po = array(md, f, 'particle_emitters')
    for i in range(pc):
        tex = struct.unpack_from('<H', md, po + i * 476 + 22)[0]
        bone = struct.unpack_from('<H', md, po + i * 476 + 20)[0]
        if tex >= n['textures']:
            faults.append(f'particle {i} texture {tex} of {n["textures"]}')
        if bone >= n['bones']:
            faults.append(f'particle {i} bone {bone} of {n["bones"]}')

    skin = open(os.path.splitext(path)[0] + '00.skin', 'rb').read()
    sc, so = struct.unpack_from('<II', skin, 0x1C)
    bc, bo = struct.unpack_from('<II', skin, 0x24)
    for i in range(bc):
        (flags, prio, shader, section, geoset, color, material, layer, texcount,
         texcombo, coordcombo, weightcombo, transcombo) = struct.unpack_from('<BbHHHhHHHHHHH', skin, bo + i * 24)
        checks = [
            (section < sc, f'section {section}/{sc}'),
            (color == -1 or color < n['colors'], f'color {color}/{n["colors"]}'),
            (material < n['materials'], f'material {material}/{n["materials"]}'),
            (texcombo + texcount <= n['texture_lookup'], f'texture combo {texcombo}+{texcount}/{n["texture_lookup"]}'),
            (coordcombo + texcount <= n['texture_unit_lookup'], f'coord combo {coordcombo}/{n["texture_unit_lookup"]}'),
            (weightcombo + texcount <= n['transparency_lookup'], f'weight combo {weightcombo}/{n["transparency_lookup"]}'),
            (transcombo + texcount <= n['texture_transform_lookup'], f'transform combo {transcombo}/{n["texture_transform_lookup"]}'),
        ]
        for ok, what in checks:
            if not ok:
                faults.append(f'batch {i}: {what}')
    return faults


if __name__ == '__main__':
    bad = 0
    for p in sys.argv[1:]:
        faults = check(p)
        if faults:
            bad += 1
            print(os.path.basename(p), '\n   ' + '\n   '.join(faults[:8]))
    print(f'{len(sys.argv) - 1 - bad} clean, {bad} with faults')
