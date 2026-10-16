-- mod-limit-break — the world tables: archetypes, who may take them, the
-- catalogue of effects, the bosses that open the fourth segment.
--
-- Idempotent: the file may be replayed. The tables are created when missing;
-- only the four archetypes, fixed by the specification, are (re)written. The
-- content tables are left as they are, so that what an administrator put in
-- them survives a replay.
--
-- The content of the archetype and catalogue tables is written by
-- 05_limit_break_content.sql (decided 2026-10-16), the module's spells by
-- 04_limit_break_spells.sql (ids 90000-90999). The boss list is NOT decided yet
-- (docs/CAHIER_DES_CHARGES.md, §16) and ships empty: the fourth segment never
-- opens until it is filled.

CREATE TABLE IF NOT EXISTS `mod_limit_break_archetype` (
  `id` TINYINT UNSIGNED NOT NULL,
  `name` VARCHAR(32) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: the four archetypes (fixed by the module)';

DELETE FROM `mod_limit_break_archetype`;
INSERT INTO `mod_limit_break_archetype` (`id`, `name`) VALUES
(1, 'heal'),
(2, 'physical damage'),
(3, 'magic damage'),
(4, 'tank');

-- Which archetypes each class may put in its slots: one row per (class, archetype).
-- class: 1 warrior, 2 paladin, 3 hunter, 4 rogue, 5 priest, 6 death knight,
-- 7 shaman, 8 mage, 9 warlock, 11 druid. Filled by 05_limit_break_content.sql.
CREATE TABLE IF NOT EXISTS `mod_limit_break_class_archetype` (
  `class` TINYINT UNSIGNED NOT NULL,
  `archetype` TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (`class`, `archetype`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: archetypes open to each class';

-- The catalogue: archetype x tier -> the spell of the effect. Sixteen rows
-- (4 archetypes x 4 tiers; tier 4 is the boss segment), filled by
-- 05_limit_break_content.sql. A spell serves one tier only and must exist on the
-- server (`spell_dbc`); the effect itself is run by the C++ module, by spell id.
CREATE TABLE IF NOT EXISTS `mod_limit_break_effect` (
  `archetype` TINYINT UNSIGNED NOT NULL,
  `tier` TINYINT UNSIGNED NOT NULL,
  `spell` INT UNSIGNED NOT NULL,
  `comment` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`archetype`, `tier`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: the effect of each archetype at each tier';

-- The bosses whose engagement opens the fourth segment, closed again at their
-- death or reset. difficulty_mask: one bit per map difficulty (1 = normal /
-- 10 normal, 2 = heroic / 25 normal, 4 = 10 heroic, 8 = 25 heroic).
CREATE TABLE IF NOT EXISTS `mod_limit_break_boss` (
  `entry` INT UNSIGNED NOT NULL,
  `difficulty_mask` TINYINT UNSIGNED NOT NULL DEFAULT 15,
  `comment` VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (`entry`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: bosses opening the fourth segment';

-- TO TRY THE FOURTH SEGMENT before the boss list exists -- not applied, copy
-- by hand into the world database, then `.reload config`:
--
-- INSERT INTO `mod_limit_break_boss` (`entry`, `difficulty_mask`, `comment`) VALUES
--   (10184, 15, 'TEST ONLY: Onyxia');
