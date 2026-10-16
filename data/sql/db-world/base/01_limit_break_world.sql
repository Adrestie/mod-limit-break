-- mod-limit-break — the world tables: archetypes, who may take them, the
-- catalogue of effects, the bosses that open the fourth segment.
--
-- Idempotent: the file may be replayed. The tables are created when missing;
-- only the four archetypes, fixed by the specification, are (re)written. The
-- content tables are left as they are, so that what an administrator put in
-- them survives a replay.
--
-- THE CONTENT IS NOT DECIDED YET (docs/CAHIER_DES_CHARGES.md, §16): which
-- archetypes each class gets, the sixteen effects, the boss list and its
-- difficulties. The three content tables therefore ship EMPTY. The module runs
-- with them empty: the gauge fills, and every slot offers "choose" with
-- nothing to choose.
--
-- Spells of the module, when they come, take identifiers 90000-90999
-- (tranche 90 of ID_RANGES.md), in `spell_dbc`.

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
-- 7 shaman, 8 mage, 9 warlock, 11 druid. The specification gives two examples
-- only (priest: heal and magic damage; druid: all four); the list for the ten
-- classes is still to be written.
CREATE TABLE IF NOT EXISTS `mod_limit_break_class_archetype` (
  `class` TINYINT UNSIGNED NOT NULL,
  `archetype` TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (`class`, `archetype`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: archetypes open to each class';

-- The catalogue: archetype x tier -> the spell the server casts. Sixteen rows
-- when complete (4 archetypes x 4 tiers; tier 4 is the boss segment). A spell
-- serves one tier only. The spell must exist on the server (Spell.dbc or
-- `spell_dbc`); the client needs nothing to cast it.
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

-- TO TRY THE MECHANISM BEFORE THE CONTENT EXISTS -- not applied, copy by hand
-- into the world database, then `.reload config`. Existing game spells as
-- stand-ins, NOT the module's effects:
--
-- INSERT INTO `mod_limit_break_class_archetype` (`class`, `archetype`) VALUES (5, 1), (5, 3);
-- INSERT INTO `mod_limit_break_effect` (`archetype`, `tier`, `spell`, `comment`) VALUES
--   (1, 1, 2061, 'TEST ONLY: Flash Heal'),
--   (3, 1, 589, 'TEST ONLY: Shadow Word: Pain');
-- INSERT INTO `mod_limit_break_boss` (`entry`, `difficulty_mask`, `comment`) VALUES
--   (10184, 15, 'TEST ONLY: Onyxia');
