-- mod-limit-break — the texts of the chat messages.
--
-- English in `module_string`, other languages in `module_string_locale`
-- (English when a language is missing). Ids match the Text enum of
-- src/LimitBreak.h and are never reused once retired. `{}` stands for a value
-- and must be kept, as many times as in English.
--
-- Idempotent: the file may be replayed.

DELETE FROM `module_string` WHERE `module` = 'mod-limit-break';
INSERT INTO `module_string` (`module`, `id`, `string`) VALUES
('mod-limit-break',  1, 'Limit Break: the module is disabled.'),
('mod-limit-break',  2, 'Limit Break: you are not in a group.'),
('mod-limit-break',  3, 'Limit Break: the gauge is paused, too few members of the group are together.'),
('mod-limit-break',  4, 'Limit Break: you are not where most of your group is.'),
('mod-limit-break',  5, 'Limit Break: the gauge has not reached its first segment.'),
('mod-limit-break',  6, 'Limit Break: no spell chosen for tier {}.'),
('mod-limit-break',  7, 'Limit Break: the spell chosen for tier {} is no longer available. Choose again.'),
('mod-limit-break',  8, 'Limit Break: not while dead.'),
('mod-limit-break',  9, 'Limit Break: tier {} unleashed.'),
('mod-limit-break', 10, 'Limit Break: choices cannot be changed in combat.'),
('mod-limit-break', 11, 'Limit Break: the tier goes from 1 to 4.'),
('mod-limit-break', 12, 'Limit Break: spell {} is not an effect of tier {}.'),
('mod-limit-break', 13, 'Limit Break: this archetype is not open to your class.'),
('mod-limit-break', 14, 'Limit Break: {} chosen for tier {}.'),
('mod-limit-break', 15, 'Limit Break: choice of tier {} cleared.'),
('mod-limit-break', 16, 'Limit Break: {} points, tier {}, active {}, {} participant(s); container: map {}, instance {}, zone {}, phase {}; fourth segment open {}.'),
('mod-limit-break', 17, 'Limit Break: your group has no gauge.'),
('mod-limit-break', 18, 'Limit Break: {} points added.'),
('mod-limit-break', 19, 'Limit Break: this effect needs a hostile target. The gauge is kept.');

DELETE FROM `module_string_locale` WHERE `module` = 'mod-limit-break';
INSERT INTO `module_string_locale` (`module`, `id`, `locale`, `string`) VALUES
('mod-limit-break',  1, 'frFR', 'Limite : le module est désactivé.'),
('mod-limit-break',  2, 'frFR', 'Limite : vous n''êtes pas dans un groupe.'),
('mod-limit-break',  3, 'frFR', 'Limite : la jauge est en pause, trop peu de membres du groupe sont réunis.'),
('mod-limit-break',  4, 'frFR', 'Limite : vous n''êtes pas là où se trouve la plus grande partie de votre groupe.'),
('mod-limit-break',  5, 'frFR', 'Limite : la jauge n''a pas atteint son premier segment.'),
('mod-limit-break',  6, 'frFR', 'Limite : aucun sort choisi pour le palier {}.'),
('mod-limit-break',  7, 'frFR', 'Limite : le sort choisi pour le palier {} n''est plus disponible. Choisissez-en un autre.'),
('mod-limit-break',  8, 'frFR', 'Limite : impossible en étant mort.'),
('mod-limit-break',  9, 'frFR', 'Limite : palier {} déclenché.'),
('mod-limit-break', 10, 'frFR', 'Limite : les choix ne se modifient pas en combat.'),
('mod-limit-break', 11, 'frFR', 'Limite : le palier va de 1 à 4.'),
('mod-limit-break', 12, 'frFR', 'Limite : le sort {} n''est pas un effet du palier {}.'),
('mod-limit-break', 13, 'frFR', 'Limite : cet archétype n''est pas ouvert à votre classe.'),
('mod-limit-break', 14, 'frFR', 'Limite : {} choisi pour le palier {}.'),
('mod-limit-break', 15, 'frFR', 'Limite : choix du palier {} effacé.'),
('mod-limit-break', 16, 'frFR', 'Limite : {} points, palier {}, active {}, {} participant(s) ; conteneur : map {}, instance {}, zone {}, phase {} ; 4e segment ouvert {}.'),
('mod-limit-break', 17, 'frFR', 'Limite : votre groupe n''a pas de jauge.'),
('mod-limit-break', 18, 'frFR', 'Limite : {} points ajoutés.'),
('mod-limit-break', 19, 'frFR', 'Limite : cet effet demande une cible hostile. La jauge est conservée.');
