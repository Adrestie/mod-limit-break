/*
 * This file is part of mod-limit-break.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
 * Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

/*
 * mod-limit-break — LES COMMANDES, chemin unique des requetes du HUD.
 *
 * .limitbreak use                    (SEC_PLAYER) declenche le palier atteint
 * .limitbreak choose <palier> <sort> (SEC_PLAYER) choisit le sort d'un palier
 *                                                 (sort 0 : efface le choix)
 * .limitbreak catalog                (SEC_PLAYER) renvoie au HUD les sorts
 *                                                 ouverts et les choix
 * .limitbreak info                   (SEC_PLAYER) la jauge du groupe en clair
 * .limitbreak fill <points>          (SEC_GAMEMASTER) ajoute des points, essais
 *
 * Le HUD (AIO) les lance au nom du joueur. Comme /run permet a n'importe qui
 * d'appeler le HUD avec ce qu'il veut, use ne porte AUCUN parametre : tout est
 * recalcule ici. choose est revalide (palier, archetype ouvert a la classe,
 * hors combat). Le flood est rejete avant tout travail, en silence.
 */

#include "LimitBreak.h"

#include "Chat.h"
#include "ChatCommand.h"
#include "Player.h"
#include "ScriptMgr.h"

using namespace Acore::ChatCommands;
using namespace LimitBreak;

class limit_break_commandscript : public CommandScript
{
public:
    limit_break_commandscript() : CommandScript("limit_break_commandscript") { }

    ChatCommandTable GetCommands() const override
    {
        static ChatCommandTable limitBreakTable =
        {
            { "use",     HandleUseCommand,     SEC_PLAYER,     Console::No },
            { "choose",  HandleChooseCommand,  SEC_PLAYER,     Console::No },
            { "catalog", HandleCatalogCommand, SEC_PLAYER,     Console::No },
            { "info",    HandleInfoCommand,    SEC_PLAYER,     Console::No },
            { "fill",    HandleFillCommand,    SEC_GAMEMASTER, Console::No },
            { "debug",   HandleDebugCommand,   SEC_GAMEMASTER, Console::No },
        };

        static ChatCommandTable commandTable =
        {
            { "limitbreak", limitBreakTable },
        };

        return commandTable;
    }

    static bool HandleUseCommand(ChatHandler* handler)
    {
        Player* player = handler->GetPlayer();
        if (!AcceptRequest(player))
            return true;

        RequestUse(handler, player);
        return true;
    }

    static bool HandleChooseCommand(ChatHandler* handler, uint32 tier, uint32 spell)
    {
        Player* player = handler->GetPlayer();
        if (!AcceptRequest(player))
            return true;

        RequestChoose(handler, player, tier, spell);
        return true;
    }

    static bool HandleCatalogCommand(ChatHandler* handler)
    {
        Player* player = handler->GetPlayer();
        if (!AcceptRequest(player))
            return true;

        SendCatalog(player);
        return true;
    }

    static bool HandleInfoCommand(ChatHandler* handler)
    {
        Player* player = handler->GetPlayer();
        if (!AcceptRequest(player))
            return true;

        if (!GetConfig().enabled)
        {
            Say(handler, TEXT_DISABLED);
            return true;
        }

        SendInfo(handler, player);
        return true;
    }

    static bool HandleDebugCommand(ChatHandler* handler)
    {
        SendDebug(handler, handler->GetPlayer());
        return true;
    }

    static bool HandleFillCommand(ChatHandler* handler, float points)
    {
        Player* player = handler->GetPlayer();
        if (!GetConfig().enabled)
        {
            Say(handler, TEXT_DISABLED);
            return true;
        }

        if (!Fill(player, points))
        {
            Say(handler, TEXT_NO_GROUP);
            return true;
        }

        Say(handler, TEXT_FILLED, Acore::StringFormat("{:.2f}", points));
        return true;
    }
};

void AddSC_limit_break_commandscript()
{
    new limit_break_commandscript();
}
