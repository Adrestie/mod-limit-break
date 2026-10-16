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
 * mod-limit-break — LES SEIZE EFFETS (4 archetypes x 4 paliers).
 *
 * Le serveur les execute lui-meme : aucun sort n'a besoin d'exister cote
 * client. Les auras (tank, ralenti, etourdissement, vulnerabilites) sont des
 * lignes de spell_dbc de la tranche 90 ; les soins et les degats sont calcules
 * ici, en % des PV max pour les soins, en multiple de la puissance des sorts
 * (PS) ou de la puissance d'attaque (PA) pour les degats, sans resistance ni
 * armure. Les repetitions (zones, meteores) sont des evenements du lanceur.
 *
 * LES VISUELS sont ceux du client 3.3.5, sans patch : les kits de visuel
 * (SpellVisualKit.dbc, SMSG_PLAY_SPELL_VISUAL) des sorts modeles, et pour les
 * zones au sol l'objet de zone (DynamicObject) du sort modele lui-meme, que le
 * client dessine comme le vrai. Le journal de combat porte le nom du sort
 * modele. Kits releves dans SpellVisual.dbc :
 *
 *   Mur protecteur (871)   impact 158       Gardien divin (70940)  impact 7815
 *   Zone anti-magie (51052) incantation 218  Esprit gardien (47788) etat 11186
 *   Priere de soins (596)  impact 12463     Hymne divin (64844)    impact 98
 *   Resurrection (2006)    impact 70        Consecration (26573)   impact 121
 *   Nova de givre (122)    incantation 160  Blizzard (42208)       impact 413
 *   Mort et decomp. (52212) impact 10865    Coup de tonnerre (6343) 356 / 283
 *   Tempete de lames (46924) 9858, (50622) impact 10847
 *   Pluie de feu (42223)   impact 76
 *
 * THREADS : l'effet part du thread monde (requete du joueur, aucune map ne
 * tourne) ; ses repetitions tournent dans le thread de la map du lanceur, et
 * s'arretent s'il en change. Elles ne lisent l'etat du thread monde (la
 * generation de l'effet du groupe) que pendant la phase A, ou il ne bouge pas.
 */

#include "LimitBreak.h"

#include "CellImpl.h"
#include "Creature.h"
#include "DynamicObject.h"
#include "GridNotifiers.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "SpellAuraEffects.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "SpellMgr.h"

#include <functional>
#include <list>
#include <unordered_map>

namespace LimitBreak
{
    thread_local bool tInOwnEffect = false;

    namespace
    {
        // Les kits de visuel (voir l'en-tete du fichier).
        enum Kits : uint32
        {
            KIT_SHIELD_WALL      = 158,
            KIT_DIVINE_GUARDIAN  = 7815,
            KIT_ANTI_MAGIC_ZONE  = 218,
            KIT_GUARDIAN_SPIRIT  = 11186,
            KIT_PRAYER_OF_HEALING = 12463,
            KIT_DIVINE_HYMN      = 98,
            KIT_RESURRECTION     = 70,
            KIT_CONSECRATION     = 121,
            KIT_FROST_NOVA       = 160,
            KIT_BLIZZARD_HIT     = 413,
            KIT_DEATH_DECAY_HIT  = 10865,
            KIT_THUNDER_CLAP     = 356,
            KIT_THUNDER_CLAP_HIT = 283,
            KIT_BLADESTORM       = 9858,
            KIT_BLADESTORM_HIT   = 10847,
            KIT_RAIN_OF_FIRE_HIT = 76,
        };

        // Les sorts modeles : zones au sol, et noms du journal de combat.
        enum Models : uint32
        {
            MODEL_PRAYER_OF_HEALING = 596,
            MODEL_DIVINE_HYMN       = 64844,
            MODEL_CONSECRATION      = 26573,
            MODEL_FROST_NOVA        = 122,
            MODEL_BLIZZARD          = 10,
            MODEL_BLIZZARD_HIT      = 42208,
            MODEL_DEATH_DECAY       = 43265,
            MODEL_DEATH_DECAY_HIT   = 52212,
            MODEL_THUNDER_CLAP      = 6343,
            MODEL_BLADESTORM_HIT    = 50622,
            MODEL_RAIN_OF_FIRE      = 5740,
            MODEL_RAIN_OF_FIRE_HIT  = 42223,
        };

        std::array<uint32, 4> const TANK_AURAS = { SPELL_TANK_1, SPELL_TANK_2, SPELL_TANK_3, SPELL_TANK_4 };

        // ---------------------------------------------------------------
        // Aucun cumul : un nouvel usage du groupe remplace l'effet en cours.
        // Ecrit dans le thread monde ; lu par les repetitions (phase A).
        // ---------------------------------------------------------------

        struct GroundRef
        {
            uint32 mapId;
            uint32 instanceId;
            ObjectGuid guid;
        };

        struct GroupEffect
        {
            uint32 generation = 0;
            std::vector<GroundRef> grounds;
        };
        std::unordered_map<ObjectGuid, GroupEffect> sEffects;

        bool IsCurrent(ObjectGuid group, uint32 generation)
        {
            auto it = sEffects.find(group);
            return it != sEffects.end() && it->second.generation == generation;
        }

        // Une repetition, portee par le lanceur.
        class RepeatEvent : public BasicEvent
        {
        public:
            RepeatEvent(Player* owner, ObjectGuid group, uint32 generation, std::function<void(Player*)> action)
                : _owner(owner), _group(group), _generation(generation),
                  _mapId(owner->GetMapId()), _instanceId(owner->GetInstanceId()), _action(std::move(action)) { }

            bool Execute(uint64 /*time*/, uint32 /*diff*/) override
            {
                if (_owner->IsInWorld() && _owner->GetMapId() == _mapId && _owner->GetInstanceId() == _instanceId
                    && IsCurrent(_group, _generation))
                    _action(_owner);
                return true;
            }

        private:
            Player* _owner;
            ObjectGuid _group;
            uint32 _generation;
            uint32 _mapId;
            uint32 _instanceId;
            std::function<void(Player*)> _action;
        };

        // ---------------------------------------------------------------
        // Les briques
        // ---------------------------------------------------------------

        void Visual(Unit* unit, uint32 kit)
        {
            if (unit && unit->IsInWorld())
                unit->SendPlaySpellVisual(kit);
        }

        bool IsBoss(Unit const* unit)
        {
            Creature const* creature = unit->ToCreature();
            return creature && (creature->isWorldBoss() || creature->IsDungeonBoss());
        }

        // Les ennemis du lanceur, vivants, a portee d'un point.
        struct EnemyInRange
        {
            Player* caster;
            Position center;
            float radius;

            bool operator()(Unit* unit) const
            {
                if (!unit->IsAlive() || !unit->IsInWorld() || unit->GetExactDist(&center) > radius)
                    return false;
                if (Creature* creature = unit->ToCreature())
                    if (creature->IsInEvadeMode())
                        return false;
                return caster->IsValidAttackTarget(unit);
            }
        };

        std::list<Unit*> EnemiesAround(Player* caster, Position const& center, float radius)
        {
            std::list<Unit*> enemies;
            EnemyInRange check{ caster, center, radius };
            Acore::UnitListSearcher<EnemyInRange> searcher(caster, enemies, check);
            Cell::VisitObjects(center.GetPositionX(), center.GetPositionY(), caster->GetMap(), searcher, radius);
            return enemies;
        }

        // Des degats calcules ici : ni resistance ni armure. Le journal de
        // combat porte le nom du sort modele.
        void Strike(Player* caster, Unit* victim, double amount, SpellSchoolMask school, uint32 logSpell)
        {
            if (amount < 1.0 || !victim->IsAlive())
                return;

            victim->EngageWithTarget(caster);

            SpellNonMeleeDamage damage(caster, victim, sSpellMgr->GetSpellInfo(logSpell), school);
            damage.damage = uint32(amount);
            damage.physicalLog = school == SPELL_SCHOOL_MASK_NORMAL;
            caster->SendSpellNonMeleeDamageLog(&damage);

            tInOwnEffect = true;
            caster->DealSpellDamage(&damage, false);
            tInOwnEffect = false;
        }

        void Heal(Player* healer, Unit* target, float pct, uint32 logSpell)
        {
            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(logSpell);
            uint32 amount = uint32(target->GetMaxHealth() * pct / 100.0f);
            if (!spellInfo || !amount || !target->IsAlive())
                return;

            HealInfo healInfo(healer, target, amount, spellInfo, spellInfo->GetSchoolMask());
            tInOwnEffect = true;
            healer->HealBySpell(healInfo);
            tInOwnEffect = false;
        }

        void Resurrect(Player* player, float pct)
        {
            if (player->IsAlive())
                return;
            player->ResurrectPlayer(pct / 100.0f);
            player->SpawnCorpseBones();
            Visual(player, KIT_RESURRECTION);
        }

        // Un effet magique nefaste de moins.
        void DispelOne(Unit* target)
        {
            for (auto const& [spellId, application] : target->GetAppliedAuras())
            {
                Aura* aura = application->GetBase();
                if (!application->IsPositive() && aura->GetSpellInfo()->Dispel == DISPEL_MAGIC)
                {
                    target->RemoveAura(application, AURA_REMOVE_BY_ENEMY_SPELL);
                    return;
                }
            }
        }

        void RestorePower(Player* player, float pct)
        {
            Powers power = player->getPowerType();
            if (uint32 max = player->GetMaxPower(power))
                player->ModifyPower(power, int32(max * pct / 100.0f));
        }

        // Une aura du module, posee par le lanceur.
        void Apply(Player* caster, Unit* target, uint32 spell)
        {
            if (target->IsAlive())
                caster->AddAura(spell, target);
        }

        // La zone au sol du sort modele : le client la dessine comme la vraie.
        ObjectGuid Ground(Player* caster, ObjectGuid group, uint32 modelSpell, Position const& center, float radius, uint32 ms)
        {
            if (!sSpellMgr->GetSpellInfo(modelSpell))
                return ObjectGuid::Empty;

            DynamicObject* ground = new DynamicObject();
            if (!ground->CreateDynamicObject(caster->GetMap()->GenerateLowGuid<HighGuid::DynamicObject>(), caster, modelSpell, center, radius, DYNAMIC_OBJECT_AREA_SPELL))
            {
                delete ground;
                return ObjectGuid::Empty;
            }
            ground->SetDuration(int32(ms));
            sEffects[group].grounds.push_back({ caster->GetMapId(), caster->GetInstanceId(), ground->GetGUID() });
            return ground->GetGUID();
        }

        void Repeat(Player* caster, ObjectGuid group, uint32 delay, std::function<void(Player*)> action)
        {
            caster->m_Events.AddEventAtOffset(new RepeatEvent(caster, group, sEffects[group].generation, std::move(action)), Milliseconds(delay));
        }

        float SpellPower(Player* player, SpellSchoolMask school)
        {
            return float(std::max<int32>(0, player->SpellBaseDamageBonusDone(school)));
        }

        float AttackPower(Player* player)
        {
            return std::max(player->GetTotalAttackPowerValue(BASE_ATTACK), player->GetTotalAttackPowerValue(RANGED_ATTACK));
        }

        // ---------------------------------------------------------------
        // Les archetypes
        // ---------------------------------------------------------------

        // TANK : chaque participant vivant.
        void Tank(Player* caster, std::vector<Player*> const& participants, uint32 spell)
        {
            uint32 kit = spell == SPELL_TANK_1 ? KIT_SHIELD_WALL
                : spell == SPELL_TANK_2 ? KIT_DIVINE_GUARDIAN
                : spell == SPELL_TANK_3 ? KIT_ANTI_MAGIC_ZONE
                : KIT_GUARDIAN_SPIRIT;

            for (Player* player : participants)
            {
                if (!player->IsAlive())
                    continue;
                Apply(caster, player, spell);
                Visual(player, kit);
            }
        }

        // SOIN : chaque participant ; aux paliers 3 et 4, les morts aussi.
        void Healing(Player* caster, ObjectGuid group, std::vector<Player*> const& participants, uint32 spell)
        {
            for (Player* player : participants)
            {
                switch (spell)
                {
                    case SPELL_HEAL_1:
                        Heal(caster, player, 35.0f, MODEL_PRAYER_OF_HEALING);
                        Visual(player, KIT_PRAYER_OF_HEALING);
                        break;
                    case SPELL_HEAL_2:
                        if (!player->IsAlive())
                            break;
                        Heal(caster, player, 70.0f, MODEL_DIVINE_HYMN);
                        DispelOne(player);
                        Visual(player, KIT_DIVINE_HYMN);
                        break;
                    default:                            // Aube, Puits de lumiere
                        if (!player->IsAlive())
                        {
                            Resurrect(player, spell == SPELL_HEAL_4 ? 50.0f : 25.0f);
                            break;
                        }
                        Heal(caster, player, 100.0f, MODEL_DIVINE_HYMN);
                        RestorePower(player, 25.0f);
                        Visual(player, KIT_DIVINE_HYMN);
                        break;
                }
            }

            if (spell != SPELL_HEAL_4)
                return;

            // Puits de lumiere : puis une zone de 5 % des PV max par seconde,
            // 10 s, autour du lanceur.
            constexpr float RADIUS = 10.0f;
            Position center = caster->GetPosition();
            Ground(caster, group, MODEL_CONSECRATION, center, RADIUS, 10500);

            std::vector<ObjectGuid> guids;
            for (Player* player : participants)
                guids.push_back(player->GetGUID());

            for (uint32 tick = 1; tick <= 10; ++tick)
                Repeat(caster, group, tick * 1000, [guids, center](Player* owner)
                {
                    for (ObjectGuid const& guid : guids)
                        if (Player* player = ObjectAccessor::GetPlayer(owner->GetMap(), guid))
                            if (player->IsAlive() && player->GetExactDist(&center) <= RADIUS)
                            {
                                Heal(owner, player, 5.0f, MODEL_CONSECRATION);
                                Visual(player, KIT_CONSECRATION);
                            }
                });
        }

        // MAGIQUE : autour de la cible hostile du lanceur.
        void Magic(Player* caster, ObjectGuid group, Unit* target, uint32 spell)
        {
            Position center = target->GetPosition();

            if (spell == SPELL_MAGIC_1)
            {
                // Eclat de givre : 10 x PS de givre a 8 m, ralenti de 50 % 4 s.
                float amount = 10.0f * SpellPower(caster, SPELL_SCHOOL_MASK_FROST);
                Visual(target, KIT_FROST_NOVA);
                for (Unit* enemy : EnemiesAround(caster, center, 8.0f))
                {
                    Strike(caster, enemy, amount, SPELL_SCHOOL_MASK_FROST, MODEL_FROST_NOVA);
                    Apply(caster, enemy, SPELL_SLOW);
                }
                return;
            }

            if (spell == SPELL_MAGIC_2)
            {
                // Orbe glaciale : 25 x PS de givre en 6 s, a 10 m, ralentit.
                float perTick = 25.0f * SpellPower(caster, SPELL_SCHOOL_MASK_FROST) / 6.0f;
                Ground(caster, group, MODEL_BLIZZARD, center, 10.0f, 6500);
                for (uint32 tick = 1; tick <= 6; ++tick)
                    Repeat(caster, group, tick * 1000, [center, perTick](Player* owner)
                    {
                        for (Unit* enemy : EnemiesAround(owner, center, 10.0f))
                        {
                            Strike(owner, enemy, perTick, SPELL_SCHOOL_MASK_FROST, MODEL_BLIZZARD_HIT);
                            Apply(owner, enemy, SPELL_SLOW);
                            Visual(enemy, KIT_BLIZZARD_HIT);
                        }
                    });
                return;
            }

            // Faille entropique : 50 x PS d'ombre en 8 s, a 12 m.
            // Devoration cosmique : la meme, et la cible principale subit
            // 15 % de degats magiques de plus pendant 15 s.
            if (spell == SPELL_MAGIC_4)
                Apply(caster, target, SPELL_MAGIC_VULN);

            float perTick = 50.0f * SpellPower(caster, SPELL_SCHOOL_MASK_SHADOW) / 8.0f;
            Ground(caster, group, MODEL_DEATH_DECAY, center, 12.0f, 8500);
            for (uint32 tick = 1; tick <= 8; ++tick)
                Repeat(caster, group, tick * 1000, [center, perTick](Player* owner)
                {
                    for (Unit* enemy : EnemiesAround(owner, center, 12.0f))
                    {
                        Strike(owner, enemy, perTick, SPELL_SCHOOL_MASK_SHADOW, MODEL_DEATH_DECAY_HIT);
                        Visual(enemy, KIT_DEATH_DECAY_HIT);
                    }
                });
        }

        // PHYSIQUE : autour de la cible hostile du lanceur.
        void Physical(Player* caster, ObjectGuid group, Unit* target, uint32 spell)
        {
            Position center = target->GetPosition();
            float ap = AttackPower(caster);

            if (spell == SPELL_PHYSICAL_1)
            {
                // Fracas : 5 x PA a 5 m, etourdit 2 s (pas les boss).
                Visual(target, KIT_THUNDER_CLAP);
                for (Unit* enemy : EnemiesAround(caster, center, 5.0f))
                {
                    Strike(caster, enemy, 5.0f * ap, SPELL_SCHOOL_MASK_NORMAL, MODEL_THUNDER_CLAP);
                    Visual(enemy, KIT_THUNDER_CLAP_HIT);
                    if (!IsBoss(enemy))
                        Apply(caster, enemy, SPELL_STUN);
                }
                return;
            }

            if (spell == SPELL_PHYSICAL_2)
            {
                // Assaut : 12 x PA en 3 impacts, a 8 m.
                ObjectGuid targetGuid = target->GetGUID();
                for (uint32 hit = 0; hit < 3; ++hit)
                {
                    auto impact = [center, ap, targetGuid](Player* owner)
                    {
                        if (Unit* main = ObjectAccessor::GetUnit(*owner, targetGuid))
                            Visual(main, KIT_BLADESTORM);
                        for (Unit* enemy : EnemiesAround(owner, center, 8.0f))
                        {
                            Strike(owner, enemy, 4.0f * ap, SPELL_SCHOOL_MASK_NORMAL, MODEL_BLADESTORM_HIT);
                            Visual(enemy, KIT_BLADESTORM_HIT);
                        }
                    };
                    if (hit == 0)
                        impact(caster);
                    else
                        Repeat(caster, group, hit * 1000, impact);
                }
                return;
            }

            // Armageddon : 25 x PA en 8 meteores sur 4 s, a 12 m.
            // Ragnarok : le meme, et l'armure de la cible baisse de 20 % 15 s.
            if (spell == SPELL_PHYSICAL_4)
                Apply(caster, target, SPELL_ARMOR_BREAK);

            float perMeteor = 25.0f * ap / 8.0f;
            Ground(caster, group, MODEL_RAIN_OF_FIRE, center, 12.0f, 4500);
            for (uint32 meteor = 1; meteor <= 8; ++meteor)
                Repeat(caster, group, meteor * 500, [center, perMeteor](Player* owner)
                {
                    for (Unit* enemy : EnemiesAround(owner, center, 12.0f))
                    {
                        Strike(owner, enemy, perMeteor, SPELL_SCHOOL_MASK_NORMAL, MODEL_RAIN_OF_FIRE_HIT);
                        Visual(enemy, KIT_RAIN_OF_FIRE_HIT);
                    }
                });
        }
    }

    bool NeedsHostileTarget(uint32 spell)
    {
        return spell >= SPELL_PHYSICAL_1 && spell <= SPELL_MAGIC_4;
    }

    Unit* HostileTargetOf(Player* player)
    {
        Unit* target = player->GetSelectedUnit();
        if (!target || !target->IsInWorld() || !target->IsAlive() || target->GetMap() != player->GetMap()
            || !player->IsValidAttackTarget(target))
            return nullptr;
        return target;
    }

    void ExecuteEffect(Player* activator, ObjectGuid group, uint32 spell, std::vector<Player*> const& participants, Unit* target)
    {
        // Aucun cumul : les repetitions et les zones de l'usage precedent
        // s'arretent, les auras de tank precedentes tombent.
        GroupEffect& previous = sEffects[group];
        ++previous.generation;
        for (GroundRef const& ref : previous.grounds)
            if (ref.mapId == activator->GetMapId() && ref.instanceId == activator->GetInstanceId())
                if (DynamicObject* ground = activator->GetMap()->GetDynamicObject(ref.guid))
                    ground->Remove();
        previous.grounds.clear();

        for (Player* player : participants)
            for (uint32 aura : TANK_AURAS)
                player->RemoveAurasDueToSpell(aura);

        if (spell >= SPELL_TANK_1 && spell <= SPELL_TANK_4)
            Tank(activator, participants, spell);
        else if (spell >= SPELL_HEAL_1 && spell <= SPELL_HEAL_4)
            Healing(activator, group, participants, spell);
        else if (spell >= SPELL_MAGIC_1 && spell <= SPELL_MAGIC_4 && target)
            Magic(activator, group, target, spell);
        else if (spell >= SPELL_PHYSICAL_1 && spell <= SPELL_PHYSICAL_4 && target)
            Physical(activator, group, target, spell);
    }

    uint32 ModifyDamage(Unit* victim, uint32 damage)
    {
        // Bastion eternel : impossible de tomber sous 1 PV.
        if (damage >= victim->GetHealth() && victim->HasAura(SPELL_TANK_4))
            return victim->GetHealth() > 1 ? victim->GetHealth() - 1 : 0;
        return damage;
    }
}
