"""
build_visuals -- the module's backported visuals, from visuals.json to the package.

    python build_visuals.py

For each visual of visuals.json, numbered from first_id (tranche 90):
  - the modern model, its skins, animations and textures, laid out by pack.py
    into data/client/<game_dir> for WarcraftXL's modern M2 plugin (no
    conversion: the client needs WarcraftXL);
  - SpellVisualEffectName (the model), SpellVisualKit (the model on the base or
    the chest of the unit), SpellVisual (that kit as the state of an aura): one
    row each, same number, written into installer.json;
  - a test spell of the same number: a 10-second persistent area at the
    caster's feet (the visual stays on the ground where it was cast), on the client (Spell.dbc,
    installer.json) and on the server (data/sql/db-world/base/07_limit_break_visual_tests.sql).
    `.cast <number>` shows the visual on oneself for 10 seconds.

Everything this script writes is regenerated from visuals.json: edit that file,
not its output.
"""

import json
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import pack  # noqa: E402

ONE = struct.unpack('<i', struct.pack('<f', 1.0))[0]
MIN_SCALE = struct.unpack('<i', struct.pack('<f', 0.01))[0]
MAX_SCALE = struct.unpack('<i', struct.pack('<f', 100.0))[0]
NAME_MASK = 16712190                             # the flags field of a localized string
ATTACH = {'head': 3, 'chest': 4, 'base': 5}      # fields of SpellVisualKit

DBC_FILES = {
    'SpellVisualEffectName.dbc': {'fields': 7, 'text_fields': [1, 2]},
    'SpellVisualKit.dbc': {'fields': 38},
    'SpellVisual.dbc': {'fields': 32},
    'Spell.dbc': {'fields': 234, 'text_fields': [[136, 151], [153, 168], [170, 185], [187, 202]]},
    'SpellVisualKitModelAttach.dbc': {'fields': 10},
}


def fbits(x):
    return struct.unpack('<i', struct.pack('<f', float(x)))[0]


def main():
    conf = json.load(open(os.path.join(HERE, 'visuals.json'), encoding='utf-8'))
    game_dir = conf['game_dir']
    out_dir = os.path.join(ROOT, 'data', 'client', *game_dir.split('\\'))
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    rows = {name: [] for name in DBC_FILES}
    sql = []
    attach_id = 90100                           # SpellVisualKitModelAttach rows
    remap = {int(k, 16): int(v, 16) for k, v in conf.get('remap', {}).items()}
    kept = [v for v in conf['visuals'] if not v.get('skip')]
    for v in kept:
        vid = v['id']
        src = os.path.join(conf['export_dir'], v['source'])
        notes = pack.pack(src, out_dir, v['name'], game_dir, v, remap)
        for n in notes:
            print(f"{v['name']}: {n}")

        model_path = game_dir + '\\' + v['name'] + '.mdx'   # the tables name models .mdx
        rows['SpellVisualEffectName.dbc'].append(
            {'0': vid, '1': v['name'], '2': model_path, '3': 0,
             '4': struct.unpack('<i', struct.pack('<f', v.get('scale', conf.get('scale', 1.0))))[0],
             '5': MIN_SCALE, '6': MAX_SCALE})

        # the kit: the model in one of its slots, or -- when it must be turned,
        # moved or shown several times -- through SpellVisualKitModelAttach rows
        kit = {'0': vid, '1': -1, '2': -1, '17': -1, '18': -1, '19': -1, '20': -1}
        rotation = v.get('rotation')
        copies = v.get('copies')
        if rotation or copies or v.get('offset'):
            yaw0, pitch, roll = rotation or (0.0, 0.0, 0.0)
            ox, oy, oz = v.get('offset', (0.0, 0.0, 0.0))
            for yaw in copies or [0.0]:
                rows['SpellVisualKitModelAttach.dbc'].append({
                    '0': attach_id, '1': vid, '2': vid, '3': -1,
                    '4': fbits(ox), '5': fbits(oy), '6': fbits(oz),
                    '7': fbits(yaw0 + yaw), '8': fbits(pitch), '9': fbits(roll)})
                attach_id += 1
        else:
            kit[str(ATTACH[v['attach']])] = vid
        rows['SpellVisualKit.dbc'].append(kit)

        # where the kit plays: on the spell's ground object (it stays where it
        # was cast), on the caster for the aura's duration (it follows), or
        # once on the caster at the cast
        mode = v.get('mode', 'ground')
        visual = {'0': vid, '10': 1, '16': -1}
        visual[{'ground': '25', 'follow': '4', 'once': '2'}[mode]] = vid
        rows['SpellVisual.dbc'].append(visual)

        if mode == 'ground':
            effect, target, radius = 27, 18, 14   # persistent area at the caster's feet
        else:
            effect, target, radius = 6, 1, 0      # aura on the caster
        label = v['label']
        rows['Spell.dbc'].append({
            '0': vid, '28': 1, '35': 101, '40': 1, '46': 1, '68': -1,
            '71': effect, '86': target, '92': radius, '95': 4, '131': vid, '133': 1,
            '136': label, '152': NAME_MASK, '169': NAME_MASK, '186': NAME_MASK, '203': NAME_MASK,
            '216': ONE, '217': ONE, '218': ONE, '225': 1,
        })
        sql.append(f"({vid}, 1, 1, 1, 1, -1, {effect}, 0, {target}, {radius}, 4, 'LB visual test: {v['name']}')")
        print(f"{vid}: {v['name']} ({mode})")

    # installer.json: the four DBC entries, the game files
    manifest_path = os.path.join(ROOT, 'installer.json')
    manifest = json.load(open(manifest_path, encoding='utf-8'))
    dbc = [d for d in manifest.get('dbc', []) if d['file'] not in DBC_FILES]
    for name, spec in DBC_FILES.items():
        entry = {'file': name, **spec, 'client': True, 'server': False, 'rows': rows[name]}
        dbc.append(entry)
    manifest['dbc'] = dbc
    manifest['game_files'] = {'sources': ['data/client'], 'owned_folders': [game_dir.replace('\\', '/')]}
    manifest['fields']['game'] = 'required'
    with open(manifest_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # the server side of the test spells
    path = os.path.join(ROOT, 'data', 'sql', 'db-world', 'base', '07_limit_break_visual_tests.sql')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('-- mod-limit-break — test spells of the backported visuals (generated by\n')
        f.write('-- tools/m2port/build_visuals.py from tools/m2port/visuals.json: do not edit).\n')
        f.write('--\n-- Each is a 10-second dummy aura whose client row (installer.json, Spell.dbc)\n')
        f.write('-- shows one visual: `.cast <id>` on oneself.\n--\n-- Idempotent: the file may be replayed.\n\n')
        f.write(f'DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 90100 AND 90199;\n')
        f.write('INSERT INTO `spell_dbc` (`ID`, `CastingTimeIndex`, `DurationIndex`, `RangeIndex`, `SchoolMask`, '
                '`EquippedItemClass`, `Effect_1`, `EffectBasePoints_1`, `ImplicitTargetA_1`, `EffectRadiusIndex_1`, `EffectAura_1`, '
                '`Name_Lang_enUS`) VALUES\n')
        f.write(',\n'.join(sql) + ';\n')
    print(f'{len(kept)} visual(s), {len(conf["visuals"]) - len(kept)} left out')


if __name__ == '__main__':
    main()
