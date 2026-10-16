# m2port — modern spell effects for the 3.3.5a client

A pipeline that takes spell models out of the local modern game and rebuilds
them for the 3.3.5a client (M2 version 264), then refuses any result the
client's own spell models would not hold.

| Step | Tool | What it does |
|---|---|---|
| 1 | `corpus.py` | the 1,565 spell models of the 3.3.5a client itself (Blizzard archives only): the reference |
| 2 | `survey.py` | reads every corpus model with `m2.py`, writes it again and reads it back (identical: 1,564 of 1,565, the last keeps its keys in an `.anim` file), and records the values they use |
| 3 | `casc.py`, `export.py` | read the local modern installation (CASC: indices, encoding, root, BLTE) and take out a model, its first skin, its textures and its `.anim` files, as wow.export does in RAW |
| 4 | `port.py` | rebuilds the model for 3.3.5 (below) |
| 5 | `validate.py` | refuses a model with an array past the end, an index past its table, tracks that do not match the sequences, or a value outside the corpus domains; all 1,564 readable corpus models pass its structural rules (`--corpus`) |
| 6 | `build_visuals.py` | from `visuals.json`: ports and validates every model (one refusal stops the build), writes the game files, the DBC rows (installer.json) and the test spells |

## The formats

`m2.py` describes every structure field by field (sequence 64 bytes, bone 88,
particle 476 in 3.3.5 and 492 from Cataclysm on, ribbon 176, light 156,
camera 100, M2Track 20, FakeAnimationBlock 16, submesh 48, batch 24). A
modern model is the MD20 of 3.3.5 inside a chunked container (MD21) with
FileDataIDs beside it (TXID textures, SFID skins, AFID animations). The header
is laid out the same; what differs:

| Item | Modern | 3.3.5 | Done by port.py |
|---|---|---|---|
| texture names | FileDataIDs (TXID), empty names | paths | path in `Spells\LimitBreak`, file copied |
| particles | 492 bytes: two bytes of multi-texture parameters where 3.3.5 has particle type and head/tail, 16 bytes more at the end, three textures packed in one field, compressed gravity vector | 476 bytes, one texture, scalar gravity | rewritten field by field |
| particle flags, blends, emitter types | bits up to 0x10000000, blends past 5, new types | bits 0x1-0x80000 (not 0x800), blends 0/1/2/4/5, types 1-3 | masked, mapped |
| particle volume | emission rates in the thousands | 99 % of spells under 2,000 particles alive | rates scaled: 800 per emitter, 2,000 per model |
| batch shaders | IDs: stage blends in bits, 0x4000 second UV set, 0x8000+ "effects" | texture combiner combos (header flag 0x08) indexed by the batch, at most two textures | translated as MultiConverter does (pairs of stage blends, two-pass split for the two-pass effects, first texture for the others); every combo produced is one the client's own spells use |
| lookups | a two-texture batch may index one entry past the end of the transparency / transform / texture lookups | the client reads both entries | the missing entry added, a copy of the first |
| materials | blend 7 (blend add), flags past 0x100 | blends 0-6 | blend 7 → add, unlit, unfogged |
| global loops | may last 0 ms | the client takes the time modulo their length | 1 ms |
| animations | keys of some sequences in `.anim` files (AFM2 chunk) | keys in the model | inlined, sequence flag 0x20 |
| animation IDs | past 505 | up to 505 | 0 (Stand) |
| cameras | layout changed (field of view track) | | dropped |
| skins | header 8 bytes longer, boneCountMax 0, submeshes past 65,535 indices | | rewritten; boneCountMax set; such submeshes dropped |

## What is not covered

- The modern "effect" shaders past 24 (e.g. 33, frequent in recent models) have
  no known 3.3.5 equivalent: their batch keeps its first texture with the
  material's blend. The effect is drawn, but simpler than the original.
- Only the first view (LOD 0) is kept.
- `validate.py` checks structure and domains: what it cannot check is how the
  result looks. That needs the game.
