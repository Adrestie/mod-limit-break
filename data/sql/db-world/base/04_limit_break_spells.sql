-- mod-limit-break — the spells of the module (ids 90000-90299 of the WoW-mods registry).
--
-- The server runs every effect itself (src/LimitBreakEffects.cpp); these rows
-- only give it what it needs:
--   90001-90016  the catalogue: one spell per archetype and tier. The tank ones
--                are the auras put on each participant; the others carry a
--                dummy effect, the C++ module doing the work;
--   90020-90023  auras that the effects put on enemies.
-- The client knows none of them (no client patch): the visuals and the combat
-- log come from game spells, see src/LimitBreakEffects.cpp.
--
-- Amounts are exact: EffectDieSides 0 makes EffectBasePoints the value.
-- Durations (SpellDuration.dbc): 39 = 2 s, 35 = 4 s, 31 = 8 s, 1 = 10 s, 8 = 15 s.
-- Auras (EffectAura): 12 stun, 33 decrease speed, 77 mechanic immunity,
-- 87 damage taken %, 101 resistance %. Effects: 3 dummy, 6 apply aura.
--
-- Idempotent: the file may be replayed.

DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 90000 AND 90099;
INSERT INTO `spell_dbc` (`ID`, `Mechanic`, `CastingTimeIndex`, `DurationIndex`, `RangeIndex`, `SchoolMask`,
  `Effect_1`, `EffectBasePoints_1`, `EffectDieSides_1`, `ImplicitTargetA_1`, `EffectAura_1`, `EffectMiscValue_1`,
  `Effect_2`, `EffectBasePoints_2`, `EffectDieSides_2`, `ImplicitTargetA_2`, `EffectAura_2`, `EffectMiscValue_2`,
  `SpellIconID`, `Name_Lang_enUS`, `Name_Lang_frFR`) VALUES
-- heal: the module heals, revives and restores
(90001, 0, 1, 0, 1, 2,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Breath of Life', 'Souffle de vie'),
(90002, 0, 1, 0, 1, 2,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Renewal', 'Renouveau'),
(90003, 0, 1, 0, 1, 2,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Dawn', 'Aube'),
(90004, 0, 1, 0, 1, 2,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Wellspring of Light', 'Puits de lumière'),
-- physical damage: the module strikes around the caster's hostile target
(90005, 0, 1, 0, 1, 1,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Shatter', 'Fracas'),
(90006, 0, 1, 0, 1, 1,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Onslaught', 'Assaut'),
(90007, 0, 1, 0, 1, 1,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Armageddon', 'Armageddon'),
(90008, 0, 1, 0, 1, 1,  3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Ragnarok', 'Ragnarök'),
-- magic damage: the module strikes around the caster's hostile target
(90009, 0, 1, 0, 1, 16, 3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Frost Shard', 'Éclat de givre'),
(90010, 0, 1, 0, 1, 16, 3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Glacial Orb', 'Orbe glaciale'),
(90011, 0, 1, 0, 1, 32, 3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Entropic Rift', 'Faille entropique'),
(90012, 0, 1, 0, 1, 32, 3, 0, 0, 1, 0, 0,  0, 0, 0, 0, 0, 0,  1, 'Cosmic Devouring', 'Dévoration cosmique'),
-- tank: the auras themselves, on each participant (damage taken, all schools)
(90013, 0, 1, 31, 1, 1, 6, -25, 0, 1, 87, 127,  0, 0, 0, 0, 0, 0,  1, 'Rampart', 'Rempart'),
(90014, 0, 1, 1,  1, 1, 6, -45, 0, 1, 87, 127,  0, 0, 0, 0, 0, 0,  1, 'Aegis', 'Égide'),
(90015, 0, 1, 1,  1, 1, 6, -70, 0, 1, 87, 127,  6, 0, 0, 1, 77, 12,  1, 'Last Rampart', 'Dernier rempart'),
(90016, 0, 1, 31, 1, 1, 6, -70, 0, 1, 87, 127,  0, 0, 0, 0, 0, 0,  1, 'Eternal Bastion', 'Bastion éternel'),
-- on enemies
(90020, 11, 1, 35, 1, 16, 6, -50, 0, 6, 33, 0,   0, 0, 0, 0, 0, 0,  1, 'Limit Break: Chill', 'Limite : transi'),
(90021, 12, 1, 39, 1, 1,  6, 0,   0, 6, 12, 0,   0, 0, 0, 0, 0, 0,  1, 'Limit Break: Stun', 'Limite : étourdi'),
(90022, 0,  1, 8,  1, 32, 6, 15,  0, 6, 87, 126, 0, 0, 0, 0, 0, 0,  1, 'Limit Break: Devoured', 'Limite : dévoré'),
(90023, 0,  1, 8,  1, 1,  6, -20, 0, 6, 101, 1,  0, 0, 0, 0, 0, 0,  1, 'Limit Break: Sundered', 'Limite : brisé');

-- No equipment requirement (the column defaults to 0, "consumable", which a
-- cast would require).
UPDATE `spell_dbc` SET `EquippedItemClass` = -1 WHERE `ID` BETWEEN 90000 AND 90099;
