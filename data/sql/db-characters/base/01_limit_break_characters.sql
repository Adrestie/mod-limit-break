-- mod-limit-break — the choices of each character: one spell per tier, four
-- tiers at most. The gauge itself is never stored.
--
-- Idempotent: the file may be replayed, it creates nothing that already exists.

CREATE TABLE IF NOT EXISTS `mod_limit_break_choice` (
  `guid` INT UNSIGNED NOT NULL,
  `tier` TINYINT UNSIGNED NOT NULL,
  `spell` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`guid`, `tier`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='LimitBreak: the spell each character chose for each tier';
