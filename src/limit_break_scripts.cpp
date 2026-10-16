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
 * mod-limit-break — les hooks du coeur, branches sur LimitBreak.cpp.
 */

#include "LimitBreak.h"

#include "ScriptMgr.h"

using namespace LimitBreak;

// Configuration, tables, et les phases B et C.
class limit_break_world : public WorldScript
{
public:
    limit_break_world() : WorldScript("limit_break_world", {
        WORLDHOOK_ON_AFTER_CONFIG_LOAD,
        WORLDHOOK_ON_STARTUP,
        WORLDHOOK_ON_UPDATE,
    }) { }

    void OnAfterConfigLoad(bool reload) override
    {
        LoadConfig();
        // Au demarrage les sorts ne sont pas encore charges : OnStartup s'en
        // charge. Un .reload config relit aussi les tables.
        if (reload)
            LoadTables();
    }

    void OnStartup() override
    {
        LoadTables();
    }

    void OnUpdate(uint32 diff) override
    {
        OnWorldUpdate(diff);
    }
};

// Phase A : le recensement, dans le thread de chaque map.
class limit_break_maps : public AllMapScript
{
public:
    limit_break_maps() : AllMapScript("limit_break_maps", {
        ALLMAPHOOK_ON_MAP_UPDATE,
    }) { }

    void OnMapUpdate(Map* map, uint32 /*diff*/) override
    {
        LimitBreak::OnMapUpdate(map);
    }
};

// Phase A : le remplissage, dans le compteur du joueur seulement.
class limit_break_units : public UnitScript
{
public:
    limit_break_units() : UnitScript("limit_break_units", true, {
        UNITHOOK_ON_HEAL,
        UNITHOOK_ON_DAMAGE,
        UNITHOOK_ON_UNIT_ENTER_COMBAT,
    }) { }

    void OnHeal(Unit* healer, Unit* receiver, uint32& gain) override
    {
        LimitBreak::OnHeal(healer, receiver, gain);
    }

    void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override
    {
        LimitBreak::OnDamage(attacker, victim, damage);
    }

    void OnUnitEnterCombat(Unit* unit, Unit* /*victim*/) override
    {
        OnEnterCombat(unit);
    }
};

// Les choix du joueur, charges a la connexion.
class limit_break_players : public PlayerScript
{
public:
    limit_break_players() : PlayerScript("limit_break_players", {
        PLAYERHOOK_ON_LOGIN,
        PLAYERHOOK_ON_LOGOUT,
        PLAYERHOOK_ON_DELETE,
    }) { }

    void OnPlayerLogin(Player* player) override
    {
        OnLogin(player);
    }

    void OnPlayerLogout(Player* player) override
    {
        OnLogout(player);
    }

    void OnPlayerDelete(ObjectGuid guid, uint32 /*accountId*/) override
    {
        OnDelete(guid);
    }
};

void AddSC_limit_break_scripts()
{
    new limit_break_world();
    new limit_break_maps();
    new limit_break_units();
    new limit_break_players();
}
