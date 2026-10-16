-- mod-limit-break — the content decided on 2026-10-16: the archetypes open to
-- each class, and the catalogue (archetype x tier -> spell of 04_limit_break_spells.sql).
--
-- Idempotent: the file may be replayed; it rewrites both tables.

-- class: 1 warrior, 2 paladin, 3 hunter, 4 rogue, 5 priest, 6 death knight,
-- 7 shaman, 8 mage, 9 warlock, 11 druid.
-- archetype: 1 heal, 2 physical damage, 3 magic damage, 4 tank.
DELETE FROM `mod_limit_break_class_archetype`;
INSERT INTO `mod_limit_break_class_archetype` (`class`, `archetype`) VALUES
(1, 2), (1, 4),
(2, 1), (2, 2), (2, 4),
(3, 2),
(4, 2),
(5, 1), (5, 3),
(6, 2), (6, 4),
(7, 1), (7, 2), (7, 3),
(8, 3),
(9, 3),
(11, 1), (11, 2), (11, 3), (11, 4);

DELETE FROM `mod_limit_break_effect`;
INSERT INTO `mod_limit_break_effect` (`archetype`, `tier`, `spell`, `comment`) VALUES
(1, 1, 90001, 'Breath of Life: 35% max health to every participant'),
(1, 2, 90002, 'Renewal: 70% max health, dispels one harmful magic effect'),
(1, 3, 90003, 'Dawn: 100% health, 25% resource; the dead rise at 25%'),
(1, 4, 90004, 'Wellspring of Light: Dawn, the dead rise at 50%, then 5%/s for 10 s around the caster'),
(2, 1, 90005, 'Shatter: 5 x AP within 5 m of the target, 2 s stun (not bosses)'),
(2, 2, 90006, 'Onslaught: 12 x AP in 3 impacts within 8 m'),
(2, 3, 90007, 'Armageddon: 25 x AP in 8 meteors over 4 s within 12 m'),
(2, 4, 90008, 'Ragnarok: Armageddon, then target armor -20% for 15 s'),
(3, 1, 90009, 'Frost Shard: 10 x SP frost within 8 m of the target, 50% slow 4 s'),
(3, 2, 90010, 'Glacial Orb: 25 x SP frost over 6 s within 10 m, slows'),
(3, 3, 90011, 'Entropic Rift: 50 x SP shadow over 8 s within 12 m'),
(3, 4, 90012, 'Cosmic Devouring: Entropic Rift, then target +15% magic damage taken 15 s'),
(4, 1, 90013, 'Rampart: -25% damage taken, 8 s'),
(4, 2, 90014, 'Aegis: -45% damage taken, 10 s'),
(4, 3, 90015, 'Last Rampart: -70% damage taken, stun immunity, 10 s'),
(4, 4, 90016, 'Eternal Bastion: -70% damage taken, cannot fall below 1 health, 8 s');
