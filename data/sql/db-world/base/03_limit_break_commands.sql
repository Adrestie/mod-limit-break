-- mod-limit-break — the help of the chat commands (.help limitbreak).
--
-- The `security` column is only there for the listing: what really gates a
-- command is the level declared in the C++ table.
--
-- Idempotent: the file may be replayed.

DELETE FROM `command` WHERE `name` = 'limitbreak' OR `name` LIKE 'limitbreak %';
INSERT INTO `command` (`name`, `security`, `help`) VALUES
('limitbreak', 0, 'Syntax: .limitbreak $subcommand\n\nThe Limit Break gauge, shared by your group. The bar of the interface uses these commands.'),
('limitbreak use', 0, 'Syntax: .limitbreak use\n\nUnleashes the spell you chose for the tier the gauge has reached, and empties the gauge.'),
('limitbreak choose', 0, 'Syntax: .limitbreak choose $tier $spell\n\nChooses the spell of a tier (1 to 4), among those open to your class. Spell 0 clears the choice. Not in combat.'),
('limitbreak catalog', 0, 'Syntax: .limitbreak catalog\n\nSends the spells open to your class, and your choices, to the interface.'),
('limitbreak info', 0, 'Syntax: .limitbreak info\n\nShows the gauge of your group.'),
('limitbreak fill', 2, 'Syntax: .limitbreak fill $points\n\nAdds points to the gauge of your group (negative: removes them). For tests.');
