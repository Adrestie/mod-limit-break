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
 * mod-limit-break — LA JAUGE DE LIMITE D'UN GROUPE.
 *
 * Reference unique : docs/CAHIER_DES_CHARGES.md.
 *
 * TROIS PHASES QUI NE SE CHEVAUCHENT JAMAIS, donc aucun verrou dans le module
 * (MapUpdate.Threads = 8 en production) :
 *
 *  A. dans chaque map, son propre thread (AllMapScript::OnMapUpdate) : la map
 *     recense ses joueurs groupes dans sa propre table (Map::CustomData) ; les
 *     hooks de degats et de soins n'ecrivent que dans un compteur propre a
 *     chaque joueur (Player::CustomData).
 *  B. WorldScript::OnUpdate, thread monde, quand aucune map ne tourne : on
 *     recolte les compteurs, on elit le conteneur de chaque groupe, on applique
 *     le bareme et on publie aux joueurs s'ils participent.
 *  C. meme passage : le HUD est pousse aux membres, a cadence basse.
 *
 * Tout l'etat partage (les jauges, les choix, la configuration, les tables)
 * n'est ecrit que dans le thread monde ; les maps ne font que le lire, et le
 * thread monde n'y touche jamais pendant qu'elles tournent. Les requetes des
 * joueurs (commandes, donc CMSG_MESSAGECHAT) sont elles aussi traitees dans le
 * thread monde, l'une apres l'autre.
 */

#ifndef MOD_LIMIT_BREAK_H
#define MOD_LIMIT_BREAK_H

#include "Chat.h"
#include "DataMap.h"
#include "ObjectGuid.h"
#include "Player.h"

#include <array>
#include <string>
#include <vector>

class Creature;
class Map;
class Unit;

namespace LimitBreak
{
    constexpr char const* MODULE = "mod-limit-break";

    // Le prefixe des messages addon que le module envoie au HUD.
    constexpr char const* ADDON_PREFIX = "LimitBreak";

    constexpr uint8 TIER_COUNT = 4;          // trois segments + le 4e (boss)

    // Les archetypes (mod_limit_break_archetype).
    enum Archetype : uint8
    {
        ARCHETYPE_HEAL     = 1,
        ARCHETYPE_PHYSICAL = 2,
        ARCHETYPE_MAGIC    = 3,
        ARCHETYPE_TANK     = 4,
    };

    // Les textes de module_string (data/sql/db-world/base/02_limit_break_strings.sql).
    enum Text : uint32
    {
        TEXT_DISABLED         = 1,
        TEXT_NO_GROUP         = 2,
        TEXT_PAUSED           = 3,
        TEXT_OUTSIDE          = 4,
        TEXT_NO_TIER          = 5,
        TEXT_NO_CHOICE        = 6,
        TEXT_BAD_SPELL        = 7,
        TEXT_DEAD             = 8,
        TEXT_USED             = 9,
        TEXT_IN_COMBAT        = 10,
        TEXT_BAD_TIER         = 11,
        TEXT_NOT_IN_CATALOG   = 12,
        TEXT_NOT_YOUR_CLASS   = 13,
        TEXT_CHOSEN           = 14,
        TEXT_CLEARED          = 15,
        TEXT_INFO             = 16,
        TEXT_INFO_NO_GAUGE    = 17,
        TEXT_FILLED           = 18,
        TEXT_NO_TARGET        = 19,
    };

    // Ce que le HUD affiche (champ "etat" du message S).
    enum HudState : uint8
    {
        HUD_OFF     = 0,     // pas de groupe, ou module coupe : barre masquee
        HUD_ACTIVE  = 1,     // participant du conteneur elu
        HUD_PAUSED  = 2,     // aucun conteneur n'atteint le plancher
        HUD_OUTSIDE = 3,     // membre du groupe, hors du conteneur elu
    };

    // ---------------------------------------------------------------------
    // Configuration (conf/mod-limit-break.conf.dist), relue par .reload config
    // ---------------------------------------------------------------------

    struct Config
    {
        bool   enabled = true;
        bool   inBattlegrounds = false;      // champs de bataille et arenes
        float  factorHeal = 1.0f;
        float  factorDamageTaken = 1.0f;
        float  factorDamageDone = 1.0f;
        std::array<float, TIER_COUNT> thresholds{ { 100.0f, 200.0f, 300.0f, 400.0f } };
        uint32 minMembers = 4;               // plancher d'activation
        uint32 updateInterval = 1000;        // ms, phases B et C
        uint32 requestCooldown = 500;        // ms, anti-flood des requetes
        uint8  outsideDisplay = 0;           // 0 masque (decide), 1 grise
        bool   countSelfHeal = true;         // §16 : regles non tranchees,
        bool   countEnvironment = true;      //       reglables en attendant
        bool   countPvP = true;
        bool   countPets = true;
    };

    Config const& GetConfig();
    void LoadConfig();

    // Les tables du monde (data/sql/db-world). Rechargees par .reload config.
    void LoadTables();

    // ---------------------------------------------------------------------
    // Le conteneur : map, instance, zone, phase
    // ---------------------------------------------------------------------

    struct ContainerKey
    {
        uint32 mapId = 0;
        uint32 instanceId = 0;
        uint32 zoneId = 0;
        uint32 phaseMask = 0;

        bool operator==(ContainerKey const& o) const
        {
            return mapId == o.mapId && instanceId == o.instanceId && zoneId == o.zoneId && phaseMask == o.phaseMask;
        }
        bool operator!=(ContainerKey const& o) const { return !(*this == o); }
        bool operator<(ContainerKey const& o) const
        {
            if (mapId != o.mapId) return mapId < o.mapId;
            if (instanceId != o.instanceId) return instanceId < o.instanceId;
            if (zoneId != o.zoneId) return zoneId < o.zoneId;
            return phaseMask < o.phaseMask;
        }
    };

    ContainerKey KeyOf(Player const* player);

    // ---------------------------------------------------------------------
    // Phase A : ce que les maps ecrivent, chacune chez elle
    // ---------------------------------------------------------------------

    // Le compteur d'un joueur (Player::CustomData). Les hooks n'y ecrivent que
    // si la phase B l'a declare participant ; la phase B le vide.
    struct PlayerCounter : public DataMap::Base
    {
        double heal = 0.0;                   // soins effectifs / PV max du soigne
        double taken = 0.0;                  // degats subis / PV max de la victime
        double done = 0.0;                   // degats infliges / PV max de l'attaquant
        ObjectGuid group;                    // groupe credite, pose en phase B
        bool participant = false;            // pose en phase B

        bool Pending() const { return heal > 0.0 || taken > 0.0 || done > 0.0; }
    };

    // Le recensement d'une map (Map::CustomData).
    struct MapCensus : public DataMap::Base
    {
        struct Entry
        {
            ObjectGuid player;
            ObjectGuid group;                // vide : plus de groupe
            ContainerKey key;
            bool excluded;                   // champ de bataille ou arene coupes
        };

        struct Boss
        {
            ObjectGuid guid;
            uint32 zoneId;
            uint32 phaseMask;
        };

        uint32 epoch = 0;                    // le dernier recensement demande fait
        std::vector<Entry> entries;
        std::vector<Boss> bosses;            // boss de la liste engages ici
    };

    void OnMapUpdate(Map* map);
    void OnHeal(Unit* healer, Unit* receiver, uint32 gain);
    void OnDamage(Unit* attacker, Unit* victim, uint32 damage);
    void OnEnterCombat(Unit* unit);

    // ---------------------------------------------------------------------
    // Phases B et C : thread monde
    // ---------------------------------------------------------------------

    void OnWorldUpdate(uint32 diff);

    // ---------------------------------------------------------------------
    // Les joueurs et leurs requetes (thread monde)
    // ---------------------------------------------------------------------

    void OnLogin(Player* player);
    void OnLogout(Player* player);
    void OnDelete(ObjectGuid guid);

    // Anti-flood, avant tout travail : faux si la requete vient trop tot.
    bool AcceptRequest(Player* player);

    // Un PlayerBot remplit la jauge mais ne la depense jamais.
    bool IsBot(Player const* player);

    // .limitbreak use : sans parametre, tout est recalcule ici.
    void RequestUse(ChatHandler* handler, Player* player);

    // .limitbreak choose <palier> <sort> : sort 0 efface le choix.
    void RequestChoose(ChatHandler* handler, Player* player, uint32 tier, uint32 spell);

    // .limitbreak catalog : les sorts ouverts a la classe et les choix.
    void SendCatalog(Player* player);

    // .limitbreak info, .limitbreak fill (MJ, essais).
    void SendInfo(ChatHandler* handler, Player* player);
    bool Fill(Player* player, float points);

    // ---------------------------------------------------------------------
    // Les effets (LimitBreakEffects.cpp)
    // ---------------------------------------------------------------------

    // Les sorts du module (spell_dbc, tranche 90). Le catalogue renvoie aux
    // seize premiers ; les quatre derniers sont des auras que les effets posent.
    enum Spells : uint32
    {
        SPELL_HEAL_1        = 90001,   // Souffle de vie
        SPELL_HEAL_2        = 90002,   // Renouveau
        SPELL_HEAL_3        = 90003,   // Aube
        SPELL_HEAL_4        = 90004,   // Puits de lumiere
        SPELL_PHYSICAL_1    = 90005,   // Fracas
        SPELL_PHYSICAL_2    = 90006,   // Assaut
        SPELL_PHYSICAL_3    = 90007,   // Armageddon
        SPELL_PHYSICAL_4    = 90008,   // Ragnarok
        SPELL_MAGIC_1       = 90009,   // Eclat de givre
        SPELL_MAGIC_2       = 90010,   // Orbe glaciale
        SPELL_MAGIC_3       = 90011,   // Faille entropique
        SPELL_MAGIC_4       = 90012,   // Devoration cosmique
        SPELL_TANK_1        = 90013,   // Rempart (aura)
        SPELL_TANK_2        = 90014,   // Egide (aura)
        SPELL_TANK_3        = 90015,   // Dernier rempart (aura)
        SPELL_TANK_4        = 90016,   // Bastion eternel (aura)
        SPELL_SLOW          = 90020,   // ralenti de 50 %, 4 s
        SPELL_STUN          = 90021,   // etourdi, 2 s
        SPELL_MAGIC_VULN    = 90022,   // +15 % de degats magiques subis, 15 s
        SPELL_ARMOR_BREAK   = 90023,   // armure -20 %, 15 s
    };

    // Vrai pendant que le module inflige ou soigne lui-meme : ses propres
    // effets ne remplissent pas la jauge. Propre a chaque thread.
    extern thread_local bool tInOwnEffect;

    // Les effets offensifs exigent une cible hostile ; sans elle, rien n'est
    // depense.
    bool NeedsHostileTarget(uint32 spell);
    Unit* HostileTargetOf(Player* player);

    // Lance l'effet. participants : ceux du conteneur elu, morts compris.
    void ExecuteEffect(Player* activator, ObjectGuid group, uint32 spell, std::vector<Player*> const& participants, Unit* target);

    // Bastion eternel : on ne tombe pas sous 1 PV (hook DealDamage, phase A).
    uint32 ModifyDamage(Unit* victim, uint32 damage);

    // UN TEXTE DE module_string dans la langue du joueur, en message systeme.
    // Un texte absent de la base ne fait pas tomber le serveur : il se tait.
    template<typename... Args>
    void Say(ChatHandler* handler, uint32 id, Args&&... args)
    {
        if (handler->GetModuleString(MODULE, id))
            handler->PSendModuleSysMessage(MODULE, id, std::forward<Args>(args)...);
    }
}

#endif
