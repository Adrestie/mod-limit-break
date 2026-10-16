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
 * mod-limit-break — la mecanique : recensement, election, jauge, paliers,
 * diffusion, requetes. Voir LimitBreak.h pour le partage des threads.
 */

#include "LimitBreak.h"

#include "Config.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupMgr.h"
#include "Log.h"
#include "Map.h"
#include "MapMgr.h"
#include "ObjectAccessor.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <map>
#include <unordered_map>
#include <unordered_set>

namespace LimitBreak
{
    namespace
    {
        // Les cles de Player::CustomData et de Map::CustomData.
        std::string const COUNTER_KEY = "LimitBreak.Counter";
        std::string const CENSUS_KEY  = "LimitBreak.Census";

        // -----------------------------------------------------------------
        // Etat du thread monde. Les maps le LISENT pendant la phase A (la
        // configuration, les tables, sEpoch) ; il n'est ECRIT que dans le
        // thread monde, quand aucune map ne tourne.
        // -----------------------------------------------------------------

        Config sConfig;

        // Le recensement demande : une map recense une fois par valeur.
        uint32 sEpoch = 1;
        uint32 sTimer = 0;

        // Les archetypes ouverts a chaque classe, un bit par archetype.
        std::array<uint8, MAX_CLASSES> sClassArchetypes{};

        // Le catalogue : (archetype, palier) -> sort.
        struct Effect
        {
            uint8 archetype;
            uint8 tier;
            uint32 spell;
        };
        std::vector<Effect> sEffects;

        // Les boss qui ouvrent le 4e segment : entree -> difficultes (bits).
        std::unordered_map<uint32, uint8> sBosses;

        // La jauge d'un groupe. Jamais en base.
        struct Gauge
        {
            double points = 0.0;
            ContainerKey container;          // le dernier conteneur elu
            bool hasContainer = false;
            bool active = false;             // faux : pause
            bool fourthOpen = false;
            std::vector<ObjectGuid> participants;
        };
        std::unordered_map<ObjectGuid, Gauge> sGauges;

        // Les quatre choix de chaque joueur connecte (0 : aucun).
        std::unordered_map<ObjectGuid, std::array<uint32, TIER_COUNT>> sChoices;

        // Anti-flood : la derniere requete acceptee de chaque joueur.
        std::unordered_map<ObjectGuid, Milliseconds> sLastRequest;

        // Les joueurs a qui une barre est affichee : a masquer s'ils perdent
        // leur groupe.
        std::unordered_set<ObjectGuid> sHudShown;

        bool IsOpenToClass(uint8 archetype, uint8 playerClass)
        {
            return playerClass < MAX_CLASSES && archetype >= 1 && archetype <= 7
                && (sClassArchetypes[playerClass] & (1 << archetype));
        }

        Effect const* FindEffect(uint8 tier, uint32 spell)
        {
            for (Effect const& effect : sEffects)
                if (effect.tier == tier && effect.spell == spell)
                    return &effect;
            return nullptr;
        }

        // Le palier atteint : le plus haut seuil franchi, le 4e seulement
        // s'il est ouvert. 0 : aucun.
        uint8 TierOf(Gauge const& gauge)
        {
            uint8 last = gauge.fourthOpen ? 4 : 3;
            uint8 tier = 0;
            for (uint8 i = 1; i <= last; ++i)
                if (gauge.points >= sConfig.thresholds[i - 1])
                    tier = i;
            return tier;
        }

        uint32 ChoiceOf(ObjectGuid guid, uint8 tier)
        {
            if (tier < 1 || tier > TIER_COUNT)
                return 0;
            auto it = sChoices.find(guid);
            return it == sChoices.end() ? 0 : it->second[tier - 1];
        }

        // Un message addon au HUD du joueur, envoye par le joueur a lui-meme :
        // le client n'accepte que ceux dont il est l'expediteur.
        void SendAddon(Player* player, std::string const& body)
        {
            WorldPacket data;
            ChatHandler::BuildChatPacket(data, CHAT_MSG_WHISPER, LANG_ADDON, player, player,
                std::string(ADDON_PREFIX) + "\t" + body);
            player->SendDirectMessage(&data);
        }

        // S;etat;points;seuil1;seuil2;seuil3;seuil4;4e ouvert;palier;sort;affichage hors conteneur
        // (le point-virgule, pas la barre : le client lit | comme un echappement)
        void SendState(Player* player, HudState state, Gauge const* gauge)
        {
            if (!gauge)
            {
                SendAddon(player, "S;0");
                return;
            }

            uint8 tier = state == HUD_ACTIVE ? TierOf(*gauge) : 0;
            SendAddon(player, Acore::StringFormat("S;{};{:.2f};{:.2f};{:.2f};{:.2f};{:.2f};{};{};{};{}",
                uint32(state), gauge->points,
                sConfig.thresholds[0], sConfig.thresholds[1], sConfig.thresholds[2], sConfig.thresholds[3],
                gauge->fourthOpen ? 1 : 0, uint32(tier), ChoiceOf(player->GetGUID(), tier),
                uint32(sConfig.outsideDisplay)));
        }

        // Le joueur que credite une unite : elle-meme si c'est un joueur, son
        // maitre si c'est un familier, un totem ou un gardien (reglage).
        Player* CreditedPlayer(Unit* unit)
        {
            if (!unit)
                return nullptr;
            if (Player* player = unit->ToPlayer())
                return player;
            if (sConfig.countPets)
                return unit->GetCharmerOrOwnerPlayerOrPlayerItself();
            return nullptr;
        }

        // Le compteur d'un joueur, seulement s'il participe.
        PlayerCounter* ParticipantCounter(Player* player)
        {
            if (!player)
                return nullptr;
            PlayerCounter* counter = player->CustomData.Get<PlayerCounter>(COUNTER_KEY);
            return counter && counter->participant ? counter : nullptr;
        }

        void HideAll()
        {
            for (ObjectGuid const& guid : sHudShown)
                if (Player* player = ObjectAccessor::FindConnectedPlayer(guid))
                    SendState(player, HUD_OFF, nullptr);
            sHudShown.clear();
        }
    }

    // =====================================================================
    // Configuration et tables
    // =====================================================================

    Config const& GetConfig()
    {
        return sConfig;
    }

    void LoadConfig()
    {
        bool wasEnabled = sConfig.enabled;

        sConfig.enabled = sConfigMgr->GetOption<bool>("LimitBreak.Enable", true);
        sConfig.inBattlegrounds = sConfigMgr->GetOption<bool>("LimitBreak.EnableInBattlegrounds", false);
        sConfig.factorHeal = std::max(0.0f, sConfigMgr->GetOption<float>("LimitBreak.Factor.heal", 1.0f));
        sConfig.factorDamageTaken = std::max(0.0f, sConfigMgr->GetOption<float>("LimitBreak.Factor.DamageTaken", 1.0f));
        sConfig.factorDamageDone = std::max(0.0f, sConfigMgr->GetOption<float>("LimitBreak.Factor.DamageDone", 1.0f));

        // Seuils cumules : chacun au moins egal au precedent.
        float previous = 0.01f;
        for (uint8 i = 0; i < TIER_COUNT; ++i)
        {
            float value = sConfigMgr->GetOption<float>(Acore::StringFormat("LimitBreak.GaugeThreshold_{}", i + 1), 100.0f * (i + 1));
            sConfig.thresholds[i] = std::max(previous, value);
            previous = sConfig.thresholds[i];
        }

        sConfig.minMembers = std::max<uint32>(1, sConfigMgr->GetOption<uint32>("LimitBreak.MinMembers", 4));
        sConfig.updateInterval = std::max<uint32>(100, sConfigMgr->GetOption<uint32>("LimitBreak.UpdateInterval", 1000));
        sConfig.requestCooldown = sConfigMgr->GetOption<uint32>("LimitBreak.RequestCooldown", 500);
        sConfig.outsideDisplay = uint8(std::min<uint32>(1, sConfigMgr->GetOption<uint32>("LimitBreak.Hud.OutsideDisplay", 0)));
        sConfig.countSelfHeal = sConfigMgr->GetOption<bool>("LimitBreak.Count.SelfHeal", true);
        sConfig.countEnvironment = sConfigMgr->GetOption<bool>("LimitBreak.Count.Environment", true);
        sConfig.countPvP = sConfigMgr->GetOption<bool>("LimitBreak.Count.PvP", true);
        sConfig.countPets = sConfigMgr->GetOption<bool>("LimitBreak.Count.Pets", true);

        // Module coupe a chaud : les barres disparaissent, les jauges aussi.
        if (wasEnabled && !sConfig.enabled)
        {
            HideAll();
            sGauges.clear();
        }
    }

    void LoadTables()
    {
        sClassArchetypes.fill(0);
        uint32 classRows = 0;
        if (QueryResult result = WorldDatabase.Query("SELECT `class`, `archetype` FROM `mod_limit_break_class_archetype`"))
        {
            do
            {
                Field* fields = result->Fetch();
                uint8 playerClass = fields[0].Get<uint8>();
                uint8 archetype = fields[1].Get<uint8>();
                if (playerClass == 0 || playerClass >= MAX_CLASSES || archetype < ARCHETYPE_HEAL || archetype > ARCHETYPE_TANK)
                {
                    LOG_ERROR("module", "mod-limit-break: mod_limit_break_class_archetype ({}, {}) ignored: unknown class or archetype.", playerClass, archetype);
                    continue;
                }
                sClassArchetypes[playerClass] |= uint8(1 << archetype);
                ++classRows;
            } while (result->NextRow());
        }

        sEffects.clear();
        if (QueryResult result = WorldDatabase.Query("SELECT `archetype`, `tier`, `spell` FROM `mod_limit_break_effect`"))
        {
            do
            {
                Field* fields = result->Fetch();
                Effect effect{ fields[0].Get<uint8>(), fields[1].Get<uint8>(), fields[2].Get<uint32>() };
                if (effect.archetype < ARCHETYPE_HEAL || effect.archetype > ARCHETYPE_TANK || effect.tier < 1 || effect.tier > TIER_COUNT)
                {
                    LOG_ERROR("module", "mod-limit-break: mod_limit_break_effect ({}, {}) ignored: unknown archetype or tier.", effect.archetype, effect.tier);
                    continue;
                }
                if (!sSpellMgr->GetSpellInfo(effect.spell))
                {
                    LOG_ERROR("module", "mod-limit-break: mod_limit_break_effect ({}, {}) ignored: spell {} does not exist.", effect.archetype, effect.tier, effect.spell);
                    continue;
                }
                if (FindEffect(effect.tier, effect.spell))
                {
                    LOG_ERROR("module", "mod-limit-break: mod_limit_break_effect ({}, {}) ignored: spell {} already serves tier {}.", effect.archetype, effect.tier, effect.spell, effect.tier);
                    continue;
                }
                sEffects.push_back(effect);
            } while (result->NextRow());
        }

        sBosses.clear();
        if (QueryResult result = WorldDatabase.Query("SELECT `entry`, `difficulty_mask` FROM `mod_limit_break_boss`"))
        {
            do
            {
                Field* fields = result->Fetch();
                sBosses[fields[0].Get<uint32>()] = fields[1].Get<uint8>();
            } while (result->NextRow());
        }

        LOG_INFO("module", ">> mod-limit-break: {} effect(s), {} class archetype(s), {} boss(es).", sEffects.size(), classRows, sBosses.size());
    }

    ContainerKey KeyOf(Player const* player)
    {
        Map const* map = player->GetMap();
        return { map->GetId(), map->GetInstanceId(), player->GetZoneId(), player->GetPhaseMask() };
    }

    // =====================================================================
    // Phase A : dans le thread de chaque map
    // =====================================================================

    void OnMapUpdate(Map* map)
    {
        if (!sConfig.enabled)
            return;

        MapCensus* census = map->CustomData.Get<MapCensus>(CENSUS_KEY);
        if (census && census->epoch == sEpoch)
            return;                                     // deja fait pour ce passage

        if (!census)
        {
            if (!map->HavePlayers())
                return;                                 // rien a recenser, rien a creer
            census = map->CustomData.GetDefault<MapCensus>(CENSUS_KEY);
        }

        census->epoch = sEpoch;
        census->entries.clear();

        // Champs de bataille et arenes : recenses quand meme, pour que la
        // barre de ceux qui y entrent soit masquee ; jamais elus.
        bool excluded = map->IsBattlegroundOrArena() && !sConfig.inBattlegrounds;

        Map::PlayerList const& players = map->GetPlayers();
        for (auto itr = players.begin(); itr != players.end(); ++itr)
        {
            Player* player = itr->GetSource();
            if (!player || !player->IsInWorld())
                continue;

            // Un joueur sans groupe n'est recense que s'il a un compteur :
            // sa derniere contribution est a recolter, sa barre a masquer.
            Group* group = player->GetGroup();
            if (!group && !player->CustomData.Get<PlayerCounter>(COUNTER_KEY))
                continue;

            census->entries.push_back({ player->GetGUID(), group ? group->GetGUID() : ObjectGuid::Empty, KeyOf(player), excluded });
        }
    }

    void OnHeal(Unit* healer, Unit* receiver, uint32 gain)
    {
        if (!sConfig.enabled || tInOwnEffect || !gain || !receiver || !receiver->GetMaxHealth())
            return;

        Player* player = CreditedPlayer(healer);
        PlayerCounter* counter = ParticipantCounter(player);
        if (!counter)
            return;

        if (!sConfig.countSelfHeal && (healer == receiver || CreditedPlayer(receiver) == player))
            return;

        counter->heal += double(gain) / double(receiver->GetMaxHealth());
    }

    void OnDamage(Unit* attacker, Unit* victim, uint32 damage)
    {
        if (!sConfig.enabled || tInOwnEffect || !damage || !victim)
            return;

        // Sans attaquant, ou contre soi-meme : degats d'environnement.
        bool environment = !attacker || attacker == victim;
        if (environment && !sConfig.countEnvironment)
            return;

        Player* attackerPlayer = environment ? nullptr : CreditedPlayer(attacker);
        Player* victimPlayer = CreditedPlayer(victim);

        if (!sConfig.countPvP && attackerPlayer && victimPlayer)
            return;

        if (victim->GetMaxHealth())
            if (PlayerCounter* counter = ParticipantCounter(victimPlayer))
                counter->taken += double(damage) / double(victim->GetMaxHealth());

        if (attackerPlayer && attacker->GetMaxHealth())
            if (PlayerCounter* counter = ParticipantCounter(attackerPlayer))
                counter->done += double(damage) / double(attacker->GetMaxHealth());
    }

    void OnEnterCombat(Unit* unit)
    {
        if (!sConfig.enabled || sBosses.empty())
            return;

        Creature* creature = unit->ToCreature();
        if (!creature)
            return;

        auto boss = sBosses.find(creature->GetEntry());
        if (boss == sBosses.end())
            return;

        Map* map = creature->GetMap();
        if (!(boss->second & (1 << uint32(map->GetDifficulty()))))
            return;

        MapCensus* census = map->CustomData.GetDefault<MapCensus>(CENSUS_KEY);
        for (MapCensus::Boss const& known : census->bosses)
            if (known.guid == creature->GetGUID())
                return;

        census->bosses.push_back({ creature->GetGUID(), creature->GetZoneId(), creature->GetPhaseMask() });
    }

    // =====================================================================
    // Phases B et C : thread monde, aucune map ne tourne
    // =====================================================================

    void OnWorldUpdate(uint32 diff)
    {
        if (!sConfig.enabled)
            return;

        sTimer += diff;
        if (sTimer < sConfig.updateInterval)
            return;
        sTimer = 0;

        // --- Le depouillement des recensements ---------------------------

        struct Seen
        {
            Player* player;
            ObjectGuid group;
            ContainerKey key;
            bool excluded;
        };
        std::vector<Seen> seen;
        std::unordered_map<uint64, MapCensus*> censusByMap;     // (map, instance)

        sMapMgr->DoForAllMaps([&](Map* map)
        {
            MapCensus* census = map->CustomData.Get<MapCensus>(CENSUS_KEY);
            if (!census)
                return;

            censusByMap[(uint64(map->GetId()) << 32) | map->GetInstanceId()] = census;

            // Le 4e segment se referme a la mort ou a la remise a zero du boss.
            census->bosses.erase(std::remove_if(census->bosses.begin(), census->bosses.end(),
                [map](MapCensus::Boss const& boss)
                {
                    Creature* creature = map->GetCreature(boss.guid);
                    return !creature || !creature->IsAlive() || !creature->IsInCombat();
                }), census->bosses.end());

            // Le recensement peut dater d'une mise a jour : seul compte le
            // joueur encore dans cette map.
            for (MapCensus::Entry const& entry : census->entries)
                if (Player* player = ObjectAccessor::GetPlayer(map, entry.player))
                {
                    Group* group = player->GetGroup();
                    seen.push_back({ player, group ? group->GetGUID() : ObjectGuid::Empty, entry.key, entry.excluded });
                }
        });

        // --- La recolte, avant l'election : la contribution du dernier
        //     instant va au groupe credite, meme si le joueur est parti ---

        for (Seen const& s : seen)
        {
            PlayerCounter* counter = s.player->CustomData.Get<PlayerCounter>(COUNTER_KEY);
            if (!counter || !counter->Pending())
                continue;

            auto gauge = sGauges.find(counter->group);
            if (gauge != sGauges.end())
                gauge->second.points += sConfig.factorHeal * counter->heal
                    + sConfig.factorDamageTaken * counter->taken
                    + sConfig.factorDamageDone * counter->done;

            counter->heal = counter->taken = counter->done = 0.0;
        }

        // --- L'election ---------------------------------------------------

        struct Tally
        {
            std::map<ContainerKey, std::vector<Player*>> byKey;  // ordre stable
            std::vector<Player*> members;
        };
        std::unordered_map<ObjectGuid, Tally> tallies;
        for (Seen const& s : seen)
            if (!s.group.IsEmpty() && !s.excluded)
            {
                Tally& tally = tallies[s.group];
                tally.byKey[s.key].push_back(s.player);
                tally.members.push_back(s.player);
            }

        std::unordered_set<Player*> participants;
        for (auto& [groupGuid, tally] : tallies)
        {
            Gauge& gauge = sGauges[groupGuid];

            // Le plus grand effectif ; a egalite, le conteneur deja actif.
            std::size_t best = 0;
            ContainerKey bestKey;
            for (auto const& [key, players] : tally.byKey)
                if (players.size() > best || (players.size() == best && gauge.hasContainer && key == gauge.container))
                {
                    best = players.size();
                    bestKey = key;
                }

            gauge.participants.clear();
            gauge.active = best >= sConfig.minMembers;
            if (!gauge.active)
                continue;                               // pause : rien ne bouge

            gauge.container = bestKey;
            gauge.hasContainer = true;
            for (Player* player : tally.byKey[bestKey])
            {
                gauge.participants.push_back(player->GetGUID());
                participants.insert(player);
            }

            // Le 4e segment : un boss de la liste engage dans le conteneur.
            gauge.fourthOpen = false;
            auto census = censusByMap.find((uint64(bestKey.mapId) << 32) | bestKey.instanceId);
            if (census != censusByMap.end())
                for (MapCensus::Boss const& boss : census->second->bosses)
                    if (boss.zoneId == bestKey.zoneId && (boss.phaseMask & bestKey.phaseMask))
                        gauge.fourthOpen = true;

            // Ni decroissance ni plafond au-dela du dernier palier ouvert ; le
            // 4e referme, l'acquis des trois premiers reste.
            gauge.points = std::min<double>(gauge.points, sConfig.thresholds[gauge.fourthOpen ? 3 : 2]);
        }

        // La jauge d'un groupe dissous disparait. Un groupe dont aucun membre
        // n'est en jeu existe toujours : sa jauge se met en pause.
        for (auto it = sGauges.begin(); it != sGauges.end();)
        {
            if (tallies.count(it->first))
            {
                ++it;
                continue;
            }

            if (!sGroupMgr->GetGroupByGUID(it->first.GetCounter()))
            {
                it = sGauges.erase(it);
                continue;
            }

            it->second.active = false;
            it->second.participants.clear();
            ++it;
        }

        // --- La publication : qui remplit la jauge, et pour quel groupe ---

        for (Seen const& s : seen)
        {
            bool participant = participants.count(s.player) != 0;
            PlayerCounter* counter = participant
                ? s.player->CustomData.GetDefault<PlayerCounter>(COUNTER_KEY)
                : s.player->CustomData.Get<PlayerCounter>(COUNTER_KEY);
            if (!counter)
                continue;
            counter->participant = participant;
            counter->group = s.group;
        }

        // --- Phase C : la diffusion -------------------------------------

        for (Seen const& s : seen)
        {
            if (IsBot(s.player))
                continue;

            ObjectGuid guid = s.player->GetGUID();
            auto gauge = s.group.IsEmpty() || s.excluded ? sGauges.end() : sGauges.find(s.group);
            if (gauge == sGauges.end())
            {
                if (sHudShown.erase(guid))
                    SendState(s.player, HUD_OFF, nullptr);
                continue;
            }

            HudState state = participants.count(s.player) ? HUD_ACTIVE
                : gauge->second.active ? HUD_OUTSIDE : HUD_PAUSED;
            SendState(s.player, state, &gauge->second);
            sHudShown.insert(guid);
        }

        // Le prochain passage veut un recensement neuf.
        ++sEpoch;
    }

    // =====================================================================
    // Les joueurs et leurs requetes (thread monde)
    // =====================================================================

    void OnLogin(Player* player)
    {
        std::array<uint32, TIER_COUNT> choices{};
        if (QueryResult result = CharacterDatabase.Query("SELECT `tier`, `spell` FROM `mod_limit_break_choice` WHERE `guid` = {}", player->GetGUID().GetCounter()))
        {
            do
            {
                Field* fields = result->Fetch();
                uint8 tier = fields[0].Get<uint8>();
                uint32 spell = fields[1].Get<uint32>();
                if (tier >= 1 && tier <= TIER_COUNT)
                    choices[tier - 1] = spell;
            } while (result->NextRow());
        }
        sChoices[player->GetGUID()] = choices;
    }

    void OnLogout(Player* player)
    {
        ObjectGuid guid = player->GetGUID();
        sChoices.erase(guid);
        sLastRequest.erase(guid);
        sHudShown.erase(guid);
    }

    void OnDelete(ObjectGuid guid)
    {
        CharacterDatabase.Execute("DELETE FROM `mod_limit_break_choice` WHERE `guid` = {}", guid.GetCounter());
    }

    bool AcceptRequest(Player* player)
    {
        Milliseconds now = GameTime::GetGameTimeMS();
        Milliseconds& last = sLastRequest[player->GetGUID()];
        if (last.count() && now - last < Milliseconds(sConfig.requestCooldown))
            return false;
        last = now;
        return true;
    }

    bool IsBot(Player const* player)
    {
        // Un PlayerBot n'a pas de connexion : sa session n'a jamais d'adresse.
        WorldSession* session = player->GetSession();
        return !session || session->GetRemoteAddress().empty();
    }

    void RequestUse(ChatHandler* handler, Player* player)
    {
        if (!sConfig.enabled)
        {
            Say(handler, TEXT_DISABLED);
            return;
        }

        if (IsBot(player))
            return;

        Group* group = player->GetGroup();
        if (!group)
        {
            Say(handler, TEXT_NO_GROUP);
            return;
        }

        auto it = sGauges.find(group->GetGUID());
        if (it == sGauges.end() || !it->second.active)
        {
            Say(handler, TEXT_PAUSED);
            return;
        }
        Gauge& gauge = it->second;

        // La presence est recalculee ici, pas reprise du dernier passage.
        if (KeyOf(player) != gauge.container
            || (player->GetMap()->IsBattlegroundOrArena() && !sConfig.inBattlegrounds))
        {
            Say(handler, TEXT_OUTSIDE);
            return;
        }

        uint8 tier = TierOf(gauge);
        if (!tier)
        {
            Say(handler, TEXT_NO_TIER);
            return;
        }

        uint32 spell = ChoiceOf(player->GetGUID(), tier);
        if (!spell)
        {
            Say(handler, TEXT_NO_CHOICE, uint32(tier));
            return;
        }

        // Le choix enregistre est revalide : le catalogue a pu changer.
        Effect const* effect = FindEffect(tier, spell);
        SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell);
        if (!effect || !IsOpenToClass(effect->archetype, player->getClass()) || !spellInfo)
        {
            Say(handler, TEXT_BAD_SPELL, uint32(tier));
            return;
        }

        if (!player->IsAlive())
        {
            Say(handler, TEXT_DEAD);
            return;
        }

        // Un effet offensif sans cible hostile est refuse, et la jauge n'est
        // pas depensee.
        Unit* target = nullptr;
        if (NeedsHostileTarget(spell))
        {
            target = HostileTargetOf(player);
            if (!target)
            {
                Say(handler, TEXT_NO_TARGET);
                return;
            }
        }

        // Le serveur execute l'effet : aucun sort n'a besoin d'exister cote
        // client. Instantane (temps d'incantation non retenu). Tous les
        // participants du conteneur, morts compris.
        std::vector<Player*> participants;
        for (ObjectGuid const& guid : gauge.participants)
            if (Player* participant = ObjectAccessor::GetPlayer(player->GetMap(), guid))
                if (KeyOf(participant) == gauge.container)
                    participants.push_back(participant);

        ExecuteEffect(player, group->GetGUID(), spell, participants, target);

        // Remise a zero, quel que soit le depassement. Les requetes sont
        // traitees l'une apres l'autre : un seul usage a la fois.
        gauge.points = 0.0;
        Say(handler, TEXT_USED, uint32(tier));

        // Le prochain passage du thread monde diffuse la jauge videe.
        sTimer = sConfig.updateInterval;
    }

    void RequestChoose(ChatHandler* handler, Player* player, uint32 tier, uint32 spell)
    {
        if (!sConfig.enabled)
        {
            Say(handler, TEXT_DISABLED);
            return;
        }

        if (IsBot(player))
            return;

        if (tier < 1 || tier > TIER_COUNT)
        {
            Say(handler, TEXT_BAD_TIER);
            return;
        }

        if (player->IsInCombat())
        {
            Say(handler, TEXT_IN_COMBAT);
            return;
        }

        ObjectGuid guid = player->GetGUID();
        if (!spell)
        {
            sChoices[guid][tier - 1] = 0;
            CharacterDatabase.Execute("DELETE FROM `mod_limit_break_choice` WHERE `guid` = {} AND `tier` = {}", guid.GetCounter(), tier);
            Say(handler, TEXT_CLEARED, tier);
        }
        else
        {
            Effect const* effect = FindEffect(uint8(tier), spell);
            if (!effect)
            {
                Say(handler, TEXT_NOT_IN_CATALOG, spell, tier);
                return;
            }

            if (!IsOpenToClass(effect->archetype, player->getClass()))
            {
                Say(handler, TEXT_NOT_YOUR_CLASS);
                return;
            }

            sChoices[guid][tier - 1] = spell;
            CharacterDatabase.Execute("REPLACE INTO `mod_limit_break_choice` (`guid`, `tier`, `spell`) VALUES ({}, {}, {})", guid.GetCounter(), tier, spell);

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell);
            char const* name = spellInfo ? spellInfo->SpellName[handler->GetSessionDbcLocale()] : nullptr;
            if (!name || !*name)
                name = spellInfo ? spellInfo->SpellName[LOCALE_enUS] : "?";
            Say(handler, TEXT_CHOSEN, std::string(name), tier);
        }

        SendCatalog(player);
        sTimer = sConfig.updateInterval;
    }

    // R : le catalogue repart de zero ; C;palier;archetype;sort;nom pour chaque
    // effet ouvert a la classe ; K;choix1;choix2;choix3;choix4 pour finir.
    void SendCatalog(Player* player)
    {
        if (!sConfig.enabled || IsBot(player))
            return;

        // Le nom vient du serveur : le client ne connait pas les sorts du module.
        LocaleConstant locale = player->GetSession()->GetSessionDbcLocale();
        SendAddon(player, "R");
        for (Effect const& effect : sEffects)
            if (IsOpenToClass(effect.archetype, player->getClass()))
            {
                std::string name;
                if (SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(effect.spell))
                {
                    char const* text = spellInfo->SpellName[locale];
                    if (!text || !*text)
                        text = spellInfo->SpellName[LOCALE_enUS];
                    name = text ? text : "";
                    name.erase(std::remove(name.begin(), name.end(), ';'), name.end());
                }
                SendAddon(player, Acore::StringFormat("C;{};{};{};{}", uint32(effect.tier), uint32(effect.archetype), effect.spell, name));
            }

        ObjectGuid guid = player->GetGUID();
        SendAddon(player, Acore::StringFormat("K;{};{};{};{}",
            ChoiceOf(guid, 1), ChoiceOf(guid, 2), ChoiceOf(guid, 3), ChoiceOf(guid, 4)));
    }

    void SendInfo(ChatHandler* handler, Player* player)
    {
        Group* group = player->GetGroup();
        auto it = group ? sGauges.find(group->GetGUID()) : sGauges.end();
        if (it == sGauges.end())
        {
            Say(handler, TEXT_INFO_NO_GAUGE);
            return;
        }

        Gauge const& gauge = it->second;
        Say(handler, TEXT_INFO, Acore::StringFormat("{:.2f}", gauge.points), uint32(TierOf(gauge)),
            gauge.active ? 1u : 0u, uint32(gauge.participants.size()),
            gauge.container.mapId, gauge.container.instanceId, gauge.container.zoneId, gauge.container.phaseMask,
            gauge.fourthOpen ? 1u : 0u);
    }

    bool Fill(Player* player, float points)
    {
        Group* group = player->GetGroup();
        if (!group)
            return false;

        Gauge& gauge = sGauges[group->GetGUID()];
        gauge.points = std::max(0.0, gauge.points + points);
        sTimer = sConfig.updateInterval;
        return true;
    }
}
