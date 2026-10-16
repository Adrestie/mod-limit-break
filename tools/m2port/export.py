"""
export -- takes spell models out of the local modern game, as wow.export would
in RAW: the model, its skins and its textures, and a manifest naming them.

    python export.py <install folder> <listfile.csv> <output folder> <model path> [...]

<model path> as in the listfile, e.g. spells/fx_aegisofironforge_areatrigger.m2.
Each model lands in <output folder>/spells/: <name>.m2, <name>.manifest.json,
<name>00.skin (and its other skins), and its textures named after the listfile
(or <FileDataID>.blp when the listfile has no name for it).
"""

import json
import os
import struct
import sys

from casc import Casc, CascError


def load_listfile(path):
    by_name, by_id = {}, {}
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if ';' not in line:
                continue
            fid, name = line.rstrip('\n').split(';', 1)
            if fid.isdigit():
                by_name[name.lower()] = int(fid)
                by_id[int(fid)] = name
    return by_name, by_id


def chunk_ids(b, tag):
    off = 0
    while off + 8 <= len(b):
        t, size = struct.unpack_from('<4sI', b, off)
        if t == tag:
            return list(struct.unpack_from('<%dI' % (size // 4), b, off + 8))
        off += 8 + size
    return []


def export(casc, by_name, by_id, out, model_path):
    fid = by_name.get(model_path.lower())
    if fid is None:
        raise CascError(f'{model_path} not in the listfile')
    folder = os.path.join(out, 'spells')
    os.makedirs(folder, exist_ok=True)
    name = os.path.splitext(os.path.basename(model_path))[0].lower()
    m2 = casc.read_fid(fid)
    open(os.path.join(folder, name + '.m2'), 'wb').write(m2)

    manifest = {'fileDataID': fid, 'textures': [], 'skins': [], 'lodSkins': []}
    for i, sid in enumerate(chunk_ids(m2, b'SFID')):
        file = f'{name}{i:02d}.skin'
        open(os.path.join(folder, file), 'wb').write(casc.read_fid(sid))
        manifest['skins'].append({'fileDataID': sid, 'file': file})
        break                                    # the first view is enough for 3.3.5
    notes = []
    for tid in chunk_ids(m2, b'TXID'):
        if tid == 0:
            continue
        base = os.path.basename(by_id.get(tid, f'{tid}.blp')).lower()
        file = base if base.endswith('.blp') else f'{tid}.blp'
        try:
            open(os.path.join(folder, file), 'wb').write(casc.read_fid(tid))
            manifest['textures'].append({'fileDataID': tid, 'file': file})
        except CascError as e:
            notes.append(f'texture {tid}: {e}')
    # external animations: AFID is (animation id u16, variation u16, FileDataID u32)
    afid = chunk_ids(m2, b'AFID')
    manifest['anims'] = []
    for k in range(0, len(afid), 2):
        anim_id, variation = afid[k] & 0xFFFF, afid[k] >> 16
        fid_ = afid[k + 1]
        if not fid_:
            continue
        file = f'{name}{anim_id:04d}-{variation:02d}.anim'
        try:
            open(os.path.join(folder, file), 'wb').write(casc.read_fid(fid_))
            manifest['anims'].append({'animID': anim_id, 'subAnimID': variation, 'fileDataID': fid_, 'file': file})
        except CascError as e:
            notes.append(f'animation {anim_id}-{variation}: {e}')
    json.dump(manifest, open(os.path.join(folder, name + '.manifest.json'), 'w'), indent=1)
    return notes


if __name__ == '__main__':
    install, listfile, out = sys.argv[1:4]
    casc = Casc(install)
    by_name, by_id = load_listfile(listfile)
    for path in sys.argv[4:]:
        try:
            notes = export(casc, by_name, by_id, out, path)
            print('ok  ', path, *notes)
        except CascError as e:
            print('FAIL', path, e)
