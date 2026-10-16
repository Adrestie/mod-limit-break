--[[
    This file is part of mod-limit-break.

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful, but
    WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
    Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program. If not, see <http://www.gnu.org/licenses/>.
]]

--[[----------------------------------------------------------------------------
    Limit Break, client side (sent by AIO).

    THE BAR: a framed gauge of the group in segments -- three, and a fourth
    while a boss of the list is engaged -- with one action slot beside it. The
    slot shows the spell of the tier REACHED only, and glows while it can be
    used; when no spell is chosen for that tier, it opens the selection window
    instead, and is greyed in combat. A small button opens the selection at
    any time out of combat.

    THE SELECTION: one line per archetype open to the class, the four tiers in
    columns. One choice per column; clicking the current choice clears it.

    Nothing is decided here. The module pushes the state (addon messages,
    prefix "LimitBreak", sent by the player to himself) at a low fixed rate;
    the buttons send requests through AIO, which runs the module's commands.

    Shift + drag moves the bar (kept per character); /limitbreak opens the
    selection.
------------------------------------------------------------------------------]]

local AIO = AIO or require("AIO")

if AIO.AddAddon() then
    return                                  -- server side: we stop here
end

local PREFIX = "LimitBreak"
local TIERS = 4

-- ---------------------------------------------------------------------------
-- Texts, in the client's language
-- ---------------------------------------------------------------------------

local FR = GetLocale() == "frFR"
local L = {
    title     = FR and "LIMITE" or "LIMIT BREAK",
    tier      = FR and "Palier %d" or "Tier %d",
    tierShort = FR and "P%d" or "T%d",
    ready     = FR and "Palier %d prêt" or "Tier %d ready",
    paused    = FR and "En pause" or "Paused",
    outside   = FR and "Hors du groupe principal" or "Away from the group",
    choose    = FR and "Choisir les effets" or "Choose the effects",
    chooseTip = FR and "Aucun sort choisi pour ce palier : cliquez pour en choisir un (hors combat)."
                    or "No spell chosen for this tier: click to choose one (out of combat).",
    useTip    = FR and "Déclenche l'effet du palier %d et vide la jauge."
                    or "Unleashes the effect of tier %d and empties the gauge.",
    noTier    = FR and "La jauge n'a pas atteint son premier segment." or "The gauge has not reached its first segment.",
    combat    = FR and "Impossible en combat." or "Not in combat.",
    empty     = FR and "Aucun effet disponible pour votre classe." or "No effect available for your class.",
    pickTip   = FR and "Clic : choisir pour ce palier. Clic sur le choix actuel : l'effacer."
                    or "Click: choose for this tier. Click the current choice: clear it.",
    footer    = FR and "Un effet par palier. Modifiable hors combat, sans coût."
                    or "One effect per tier. Can be changed out of combat, for free.",
    boss      = FR and "4e segment : ouvert pendant un combat contre un boss de raid"
                    or "4th segment: open while fighting a raid boss",
    bossOpen  = FR and "Boss engagé : 4e segment ouvert" or "Boss engaged: 4th segment open",
    moveTip   = FR and "Maj + glisser : déplacer la barre" or "Shift + drag: move the bar",
    points    = FR and "%d / %d points" or "%d / %d points",
    archetypes = {
        [1] = FR and "Soin" or "Heal",
        [2] = FR and "Dégâts physiques" or "Physical damage",
        [3] = FR and "Dégâts magiques" or "Magic damage",
        [4] = FR and "Tank" or "Tank",
    },
}

-- What each effect does, for the tooltips (the client knows none of the
-- module's spells; their names come from the server).
local DESCRIPTIONS = FR and {
    [90001] = "Rend 35 % de leurs points de vie à tous les participants.",
    [90002] = "Rend 70 % de leurs points de vie et dissipe un effet magique néfaste.",
    [90003] = "Rend toute la vie et 25 % de la ressource ; les morts se relèvent à 25 %.",
    [90004] = "Comme Aube, les morts se relèvent à 50 % ; puis 5 % de vie par seconde pendant 10 s autour de vous.",
    [90005] = "5 × puissance d'attaque à 5 m de la cible, étourdit 2 s (pas les boss).",
    [90006] = "12 × puissance d'attaque en 3 impacts, à 8 m de la cible.",
    [90007] = "25 × puissance d'attaque en 8 météores sur 4 s, à 12 m de la cible.",
    [90008] = "Comme Armageddon, et l'armure de la cible baisse de 20 % pendant 15 s.",
    [90009] = "10 × puissance des sorts de givre à 8 m de la cible, ralentit de 50 % pendant 4 s.",
    [90010] = "25 × puissance des sorts de givre en 6 s, à 10 m de la cible ; ralentit.",
    [90011] = "50 × puissance des sorts d'ombre en 8 s, à 12 m de la cible.",
    [90012] = "Comme Faille entropique, et la cible subit 15 % de dégâts magiques de plus pendant 15 s.",
    [90013] = "Chaque participant subit 25 % de dégâts en moins pendant 8 s.",
    [90014] = "Chaque participant subit 45 % de dégâts en moins pendant 10 s.",
    [90015] = "70 % de dégâts en moins et insensible aux étourdissements pendant 10 s.",
    [90016] = "70 % de dégâts en moins et impossible de tomber sous 1 point de vie pendant 8 s.",
} or {
    [90001] = "Every participant regains 35% of their health.",
    [90002] = "Restores 70% health and dispels one harmful magic effect.",
    [90003] = "Restores all health and 25% of the resource; the dead rise at 25%.",
    [90004] = "As Dawn, the dead rise at 50%; then 5% health per second for 10 s around you.",
    [90005] = "5 x attack power within 5 m of the target, 2 s stun (not bosses).",
    [90006] = "12 x attack power in 3 impacts within 8 m of the target.",
    [90007] = "25 x attack power in 8 meteors over 4 s within 12 m of the target.",
    [90008] = "As Armageddon, and the target's armor drops by 20% for 15 s.",
    [90009] = "10 x frost spell power within 8 m of the target, 50% slow for 4 s.",
    [90010] = "25 x frost spell power over 6 s within 10 m of the target; slows.",
    [90011] = "50 x shadow spell power over 8 s within 12 m of the target.",
    [90012] = "As Entropic Rift, and the target takes 15% more magic damage for 15 s.",
    [90013] = "Every participant takes 25% less damage for 8 s.",
    [90014] = "Every participant takes 45% less damage for 10 s.",
    [90015] = "70% less damage taken and immune to stuns for 10 s.",
    [90016] = "70% less damage taken and cannot fall below 1 health for 8 s.",
}

-- The icons: the game spell each effect is modelled on.
local MODEL_SPELLS = {
    [90001] = 596,   [90002] = 64843, [90003] = 2006,  [90004] = 26573,
    [90005] = 6343,  [90006] = 46924, [90007] = 5740,  [90008] = 64382,
    [90009] = 122,   [90010] = 10,    [90011] = 43265, [90012] = 32379,
    [90013] = 871,   [90014] = 70940, [90015] = 51052, [90016] = 47788,
}

local ARCHETYPE_ICONS = {
    [1] = "Interface\\Icons\\Spell_Holy_FlashHeal",
    [2] = "Interface\\Icons\\Ability_MeleeDamage",
    [3] = "Interface\\Icons\\Spell_Fire_FlameBolt",
    [4] = "Interface\\Icons\\Ability_Warrior_DefensiveStance",
}
local ARCHETYPE_COLORS = {
    [1] = { 0.35, 1.0, 0.45 },
    [2] = { 1.0, 0.55, 0.25 },
    [3] = { 0.55, 0.6, 1.0 },
    [4] = { 0.75, 0.75, 0.8 },
}
local CHOOSE_ICON = "Interface\\Icons\\INV_Misc_Book_09"
local BAR_TEXTURE = "Interface\\TargetingFrame\\UI-StatusBar"

-- Segment colors: filling, full, and the boss segment.
local COLOR_FILL = { 0.15, 0.55, 1.0 }
local COLOR_FULL = { 1.0, 0.72, 0.1 }
local COLOR_BOSS = { 0.75, 0.3, 1.0 }

-- ---------------------------------------------------------------------------
-- The state, as the module sends it
-- ---------------------------------------------------------------------------

local HUD_OFF, HUD_ACTIVE, HUD_PAUSED, HUD_OUTSIDE = 0, 1, 2, 3

local state = {
    hud = HUD_OFF, points = 0, thresholds = { 100, 200, 300, 400 },
    fourthOpen = false, tier = 0, spell = 0, outsideDisplay = 0,
}
local catalog = {}                          -- catalog[tier] = { {archetype, spell}, ... }
local choices = { 0, 0, 0, 0 }
local archetypeOf = {}                      -- archetypeOf[spell] = archetype
local spellNames = {}                       -- spellNames[spell] = name sent by the module

local function SpellLabel(spell)
    local name = spellNames[spell] or GetSpellInfo(spell)
    if name and name ~= "" then
        return name
    end
    local archetype = archetypeOf[spell]
    return (archetype and L.archetypes[archetype] or "?") .. " (#" .. spell .. ")"
end

local function SpellIcon(spell)
    local model = MODEL_SPELLS[spell]
    local _, _, icon = GetSpellInfo(model or spell)
    return icon or ARCHETYPE_ICONS[archetypeOf[spell] or 0] or CHOOSE_ICON
end

local function InCombat()
    return InCombatLockdown() or UnitAffectingCombat("player")
end

local function SetBackdropDark(frame, edge)
    frame:SetBackdrop({
        bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
        edgeFile = edge or "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = true, tileSize = 16, edgeSize = 14,
        insets = { left = 3, right = 3, top = 3, bottom = 3 },
    })
    frame:SetBackdropColor(0.04, 0.04, 0.08, 0.88)
    frame:SetBackdropBorderColor(0.55, 0.55, 0.65, 1)
end

-- ---------------------------------------------------------------------------
-- The bar
-- ---------------------------------------------------------------------------

local SEG_W, SEG_H, SEG_GAP, SLOT, PAD = 64, 16, 4, 40, 10

local bar = CreateFrame("Frame", "LimitBreakBar", UIParent)
bar:SetSize(PAD + TIERS * SEG_W + (TIERS - 1) * SEG_GAP + 10 + SLOT + PAD, SLOT + 2 * PAD + 6)
bar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 180)
bar:SetMovable(true)
bar:EnableMouse(true)
bar:RegisterForDrag("LeftButton")
bar:SetScript("OnDragStart", function(self) if IsShiftKeyDown() then self:StartMoving() end end)
bar:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
SetBackdropDark(bar)
bar:Hide()

local title = bar:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
title:SetPoint("TOPLEFT", bar, "TOPLEFT", PAD, -7)
title:SetText(L.title)

local status = bar:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
status:SetPoint("LEFT", title, "RIGHT", 8, 0)

local segments = {}
for i = 1, TIERS do
    local holder = CreateFrame("Frame", nil, bar)
    holder:SetSize(SEG_W + 4, SEG_H + 4)
    holder:SetPoint("TOPLEFT", bar, "TOPLEFT", PAD - 2 + (i - 1) * (SEG_W + SEG_GAP), -22)
    holder:SetBackdrop({
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", edgeSize = 8,
        insets = { left = 2, right = 2, top = 2, bottom = 2 },
    })
    holder:SetBackdropBorderColor(0.4, 0.4, 0.5, 1)

    local seg = CreateFrame("StatusBar", nil, holder)
    seg:SetPoint("TOPLEFT", 2, -2)
    seg:SetPoint("BOTTOMRIGHT", -2, 2)
    seg:SetStatusBarTexture(BAR_TEXTURE)
    seg:SetMinMaxValues(0, 1)
    seg:SetValue(0)

    local bg = seg:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetTexture(BAR_TEXTURE)
    bg:SetVertexColor(0.08, 0.08, 0.12, 0.9)

    -- a soft light on the top half, for depth
    local shine = seg:CreateTexture(nil, "OVERLAY")
    shine:SetPoint("TOPLEFT")
    shine:SetPoint("TOPRIGHT")
    shine:SetHeight(SEG_H / 2)
    shine:SetTexture(1, 1, 1, 0.08)

    local label = seg:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    label:SetPoint("CENTER")
    label:SetText(L.tierShort:format(i))

    local lock = seg:CreateTexture(nil, "OVERLAY")
    lock:SetSize(12, 12)
    lock:SetPoint("CENTER")
    lock:SetTexture("Interface\\LFGFrame\\UI-LFG-ICON-LOCK")
    lock:Hide()

    holder:EnableMouse(true)
    holder:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:SetText(L.tier:format(i))
        local low = i > 1 and state.thresholds[i - 1] or 0
        GameTooltip:AddLine(L.points:format(math.max(0, math.min(state.points, state.thresholds[i]) - low), state.thresholds[i] - low), 1, 1, 1)
        if i == TIERS then
            GameTooltip:AddLine(state.fourthOpen and L.bossOpen or L.boss, 0.8, 0.5, 1, true)
        end
        if choices[i] and choices[i] > 0 then
            GameTooltip:AddLine(SpellLabel(choices[i]), 1, 0.82, 0)
        end
        GameTooltip:AddLine(L.moveTip, 0.5, 0.5, 0.5)
        GameTooltip:Show()
    end)
    holder:SetScript("OnLeave", function() GameTooltip:Hide() end)

    segments[i] = { holder = holder, bar = seg, label = label, lock = lock }
end

-- The action slot: the spell of the tier reached, or the way to choose one.
local slot = CreateFrame("Button", "LimitBreakSlot", bar)
slot:SetSize(SLOT, SLOT)
slot:SetPoint("RIGHT", bar, "RIGHT", -PAD, -1)
slot:SetNormalTexture(CHOOSE_ICON)
slot:GetNormalTexture():SetTexCoord(0.07, 0.93, 0.07, 0.93)
slot:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
slot:SetPushedTexture("Interface\\Buttons\\UI-Quickslot-Depress")

local slotBorder = slot:CreateTexture(nil, "OVERLAY")
slotBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
slotBorder:SetPoint("TOPLEFT", -12, 12)
slotBorder:SetPoint("BOTTOMRIGHT", 12, -12)

-- the glow of a slot that can be used, pulsing
local glow = slot:CreateTexture(nil, "OVERLAY")
glow:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
glow:SetBlendMode("ADD")
glow:SetPoint("CENTER")
glow:SetSize(SLOT * 1.9, SLOT * 1.9)
glow:SetVertexColor(1, 0.8, 0.2)
glow:Hide()

local pulse = 0
slot:SetScript("OnUpdate", function(_, elapsed)
    if glow:IsShown() then
        pulse = pulse + elapsed * 3
        glow:SetAlpha(0.55 + 0.45 * math.sin(pulse))
    end
end)

-- The small button that opens the selection at any time.
local gear = CreateFrame("Button", nil, bar)
gear:SetSize(14, 14)
gear:SetPoint("TOPRIGHT", bar, "TOPRIGHT", -PAD - SLOT - 6, -6)
gear:SetNormalTexture("Interface\\Icons\\INV_Misc_Book_09")
gear:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")

-- ---------------------------------------------------------------------------
-- The selection window: one line per archetype, one column per tier
-- ---------------------------------------------------------------------------

local CELL, CELL_GAP, ROW_LABEL_W, HEADER_H = 40, 14, 150, 22

local picker = CreateFrame("Frame", "LimitBreakPicker", UIParent)
picker:SetSize(40 + ROW_LABEL_W + TIERS * (CELL + CELL_GAP), 120)
picker:SetPoint("CENTER")
picker:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background-Dark",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Gold-Border",
    tile = true, tileSize = 32, edgeSize = 32,
    insets = { left = 11, right = 12, top = 12, bottom = 11 },
})
picker:SetMovable(true)
picker:EnableMouse(true)
picker:RegisterForDrag("LeftButton")
picker:SetScript("OnDragStart", picker.StartMoving)
picker:SetScript("OnDragStop", picker.StopMovingOrSizing)
picker:SetFrameStrata("DIALOG")
picker:Hide()
tinsert(UISpecialFrames, "LimitBreakPicker")

local header = picker:CreateTexture(nil, "ARTWORK")
header:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
header:SetSize(300, 64)
header:SetPoint("TOP", 0, 12)

local pickerTitle = picker:CreateFontString(nil, "OVERLAY", "GameFontNormal")
pickerTitle:SetPoint("TOP", header, "TOP", 0, -14)
pickerTitle:SetText(L.choose)

local close = CreateFrame("Button", nil, picker, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", -6, -6)

local pickerEmpty = picker:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
pickerEmpty:SetPoint("CENTER")
pickerEmpty:SetText(L.empty)

local footer = picker:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
footer:SetPoint("BOTTOM", 0, 18)
footer:SetText(L.footer)

local GRID_LEFT, GRID_TOP = 22 + ROW_LABEL_W, -40

-- column headers
local columnHeaders = {}
for tier = 1, TIERS do
    local text = picker:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    text:SetPoint("TOP", picker, "TOPLEFT", GRID_LEFT + (tier - 1) * (CELL + CELL_GAP) + CELL / 2, GRID_TOP)
    text:SetText(L.tier:format(tier))
    columnHeaders[tier] = text
end

local rows = {}                             -- rows[i] = { label, icon, line, cells[tier] }

local function PickerCell(row, tier)
    local cell = row.cells[tier]
    if cell then
        return cell
    end
    cell = CreateFrame("Button", nil, picker)
    cell:SetSize(CELL, CELL)
    cell:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")

    cell.icon = cell:CreateTexture(nil, "ARTWORK")
    cell.icon:SetAllPoints()
    cell.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)

    cell.border = cell:CreateTexture(nil, "OVERLAY")
    cell.border:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    cell.border:SetPoint("TOPLEFT", -12, 12)
    cell.border:SetPoint("BOTTOMRIGHT", 12, -12)

    cell.selected = cell:CreateTexture(nil, "OVERLAY")
    cell.selected:SetTexture("Interface\\Buttons\\CheckButtonHilight")
    cell.selected:SetBlendMode("ADD")
    cell.selected:SetAllPoints()

    cell.ring = cell:CreateTexture(nil, "OVERLAY")
    cell.ring:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    cell.ring:SetBlendMode("ADD")
    cell.ring:SetPoint("CENTER")
    cell.ring:SetSize(CELL * 1.85, CELL * 1.85)
    cell.ring:SetVertexColor(1, 0.82, 0.2)

    cell:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(SpellLabel(self.spell), 1, 0.82, 0)
        GameTooltip:AddLine(L.archetypes[self.archetype] .. " - " .. L.tier:format(self.tier), 0.6, 0.8, 1)
        if DESCRIPTIONS[self.spell] then
            GameTooltip:AddLine(DESCRIPTIONS[self.spell], 1, 1, 1, true)
        end
        GameTooltip:AddLine(L.pickTip, 0.5, 0.5, 0.5, true)
        GameTooltip:Show()
    end)
    cell:SetScript("OnLeave", function() GameTooltip:Hide() end)
    cell:SetScript("OnClick", function(self)
        if InCombat() then
            UIErrorsFrame:AddMessage(L.combat, 1, 0.1, 0.1)
            return
        end
        -- clicking the current choice clears it
        local spell = choices[self.tier] == self.spell and 0 or self.spell
        AIO.Handle("LimitBreak", "Choose", self.tier, spell)
    end)
    row.cells[tier] = cell
    return cell
end

local function PickerRow(index)
    local row = rows[index]
    if row then
        return row
    end
    row = { cells = {} }
    row.line = picker:CreateTexture(nil, "BORDER")
    row.line:SetTexture(1, 1, 1, 0.04)
    row.icon = picker:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(26, 26)
    row.icon:SetTexCoord(0.07, 0.93, 0.07, 0.93)
    row.label = picker:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
    row.label:SetJustifyH("LEFT")
    rows[index] = row
    return row
end

local function RefreshPicker()
    -- the archetypes that have at least one effect, in their order
    local present = {}
    for tier = 1, TIERS do
        for _, entry in ipairs(catalog[tier] or {}) do
            present[entry.archetype] = true
        end
    end
    local archetypes = {}
    for archetype = 1, 4 do
        if present[archetype] then
            archetypes[#archetypes + 1] = archetype
        end
    end

    local combat = InCombat()
    local rowH = CELL + CELL_GAP
    for index, archetype in ipairs(archetypes) do
        local row = PickerRow(index)
        local top = GRID_TOP - HEADER_H - (index - 1) * rowH
        local color = ARCHETYPE_COLORS[archetype]

        row.line:ClearAllPoints()
        row.line:SetPoint("TOPLEFT", picker, "TOPLEFT", 16, top + 4)
        row.line:SetPoint("TOPRIGHT", picker, "TOPRIGHT", -16, top + 4)
        row.line:SetHeight(rowH - 6)
        row.line:SetTexture(color[1], color[2], color[3], index % 2 == 0 and 0.05 or 0.09)
        row.line:Show()

        row.icon:ClearAllPoints()
        row.icon:SetPoint("TOPLEFT", picker, "TOPLEFT", 22, top - (CELL - 26) / 2)
        row.icon:SetTexture(ARCHETYPE_ICONS[archetype])
        row.icon:Show()

        row.label:ClearAllPoints()
        row.label:SetPoint("LEFT", row.icon, "RIGHT", 8, 0)
        row.label:SetText(L.archetypes[archetype])
        row.label:SetTextColor(color[1], color[2], color[3])
        row.label:Show()

        for tier = 1, TIERS do
            local spell
            for _, entry in ipairs(catalog[tier] or {}) do
                if entry.archetype == archetype then
                    spell = entry.spell
                end
            end
            local cell = PickerCell(row, tier)
            if spell then
                cell.tier, cell.archetype, cell.spell = tier, archetype, spell
                cell:ClearAllPoints()
                cell:SetPoint("TOPLEFT", picker, "TOPLEFT", GRID_LEFT + (tier - 1) * (CELL + CELL_GAP), top)
                cell.icon:SetTexture(SpellIcon(spell))
                local chosen = choices[tier] == spell
                local otherChosen = choices[tier] and choices[tier] > 0 and not chosen
                cell.icon:SetDesaturated(combat or otherChosen)
                cell.icon:SetVertexColor(otherChosen and 0.6 or 1, otherChosen and 0.6 or 1, otherChosen and 0.6 or 1)
                if chosen then cell.selected:Show(); cell.ring:Show() else cell.selected:Hide(); cell.ring:Hide() end
                cell:Show()
            else
                cell:Hide()
            end
        end
    end
    for index = #archetypes + 1, #rows do
        local row = rows[index]
        row.line:Hide(); row.icon:Hide(); row.label:Hide()
        for _, cell in pairs(row.cells) do cell:Hide() end
    end

    local height = -GRID_TOP + HEADER_H + math.max(1, #archetypes) * rowH + 40
    picker:SetHeight(height)
    for tier = 1, TIERS do
        if #archetypes > 0 then columnHeaders[tier]:Show() else columnHeaders[tier]:Hide() end
    end
    if #archetypes > 0 then pickerEmpty:Hide() else pickerEmpty:Show() end
end

local function OpenPicker()
    if InCombat() then
        UIErrorsFrame:AddMessage(L.combat, 1, 0.1, 0.1)
        return
    end
    RefreshPicker()
    picker:Show()
end

-- ---------------------------------------------------------------------------
-- Drawing the bar
-- ---------------------------------------------------------------------------

local function Refresh()
    if state.hud == HUD_OFF or (state.hud == HUD_OUTSIDE and state.outsideDisplay == 0) then
        bar:Hide()
        return
    end
    bar:Show()

    local live = state.hud == HUD_ACTIVE
    bar:SetAlpha(live and 1 or 0.5)
    if state.hud == HUD_PAUSED then
        status:SetText("|cff999999" .. L.paused .. "|r")
    elseif state.hud == HUD_OUTSIDE then
        status:SetText("|cff999999" .. L.outside .. "|r")
    elseif state.tier > 0 then
        status:SetText("|cffffd100" .. L.ready:format(state.tier) .. "|r")
    else
        status:SetText("")
    end

    -- each segment fills between its threshold and the previous one
    local low = 0
    for i = 1, TIERS do
        local high = state.thresholds[i] or low
        local s = segments[i]
        local fill = high > low and (state.points - low) / (high - low) or 0
        fill = math.max(0, math.min(1, fill))
        s.bar:SetValue(fill)

        local color = fill >= 1 and COLOR_FULL or (i == TIERS and COLOR_BOSS or COLOR_FILL)
        s.bar:SetStatusBarColor(color[1], color[2], color[3])
        if fill >= 1 then
            s.holder:SetBackdropBorderColor(1, 0.82, 0.2, 1)
        else
            s.holder:SetBackdropBorderColor(0.4, 0.4, 0.5, 1)
        end
        low = high
    end

    local boss = segments[TIERS]
    if state.fourthOpen then
        boss.holder:SetAlpha(1)
        boss.lock:Hide()
        boss.label:Show()
    else
        boss.holder:SetAlpha(0.45)
        boss.bar:SetValue(0)
        boss.lock:Show()
        boss.label:Hide()
    end

    -- the slot: the spell of the tier reached, or the way to choose one
    local combat = InCombat()
    if live and state.tier > 0 and state.spell > 0 then
        slot:SetNormalTexture(SpellIcon(state.spell))
        slot:GetNormalTexture():SetTexCoord(0.07, 0.93, 0.07, 0.93)
        slot:GetNormalTexture():SetDesaturated(false)
        slot:Enable()
        slot.mode = "use"
        glow:Show()
    elseif live and state.tier > 0 then
        slot:SetNormalTexture(CHOOSE_ICON)
        slot:GetNormalTexture():SetTexCoord(0.07, 0.93, 0.07, 0.93)
        slot:GetNormalTexture():SetDesaturated(combat)
        if combat then slot:Disable() else slot:Enable() end
        slot.mode = "choose"
        glow:Hide()
    else
        slot:SetNormalTexture(CHOOSE_ICON)
        slot:GetNormalTexture():SetTexCoord(0.07, 0.93, 0.07, 0.93)
        slot:GetNormalTexture():SetDesaturated(true)
        slot:Disable()
        slot.mode = nil
        glow:Hide()
    end

    gear:GetNormalTexture():SetDesaturated(combat)
    if combat then gear:Disable() else gear:Enable() end
end

slot:SetScript("OnClick", function(self)
    if self.mode == "use" then
        AIO.Handle("LimitBreak", "Use")
    elseif self.mode == "choose" then
        OpenPicker()
    end
end)
slot:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    if self.mode == "use" then
        GameTooltip:SetText(SpellLabel(state.spell), 1, 0.82, 0)
        if DESCRIPTIONS[state.spell] then
            GameTooltip:AddLine(DESCRIPTIONS[state.spell], 1, 1, 1, true)
        end
        GameTooltip:AddLine(L.useTip:format(state.tier), 0.6, 0.8, 1, true)
    elseif self.mode == "choose" then
        GameTooltip:SetText(L.choose)
        GameTooltip:AddLine(L.chooseTip, 1, 1, 1, true)
    else
        GameTooltip:SetText(L.title)
        GameTooltip:AddLine(L.noTier, 1, 1, 1, true)
    end
    GameTooltip:Show()
end)
slot:SetScript("OnLeave", function() GameTooltip:Hide() end)

gear:SetScript("OnClick", OpenPicker)
gear:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
    GameTooltip:SetText(L.choose)
    GameTooltip:Show()
end)
gear:SetScript("OnLeave", function() GameTooltip:Hide() end)

-- ---------------------------------------------------------------------------
-- The module
-- ---------------------------------------------------------------------------

local function Split(text)
    local fields = {}
    for field in (text .. ";"):gmatch("([^;]*);") do
        fields[#fields + 1] = field
    end
    return fields
end

local function OnModuleMessage(text)
    local f = Split(text)
    local kind = f[1]
    if kind == "S" then
        state.hud = tonumber(f[2]) or HUD_OFF
        if state.hud ~= HUD_OFF then
            state.points = tonumber(f[3]) or 0
            for i = 1, TIERS do
                state.thresholds[i] = tonumber(f[3 + i]) or state.thresholds[i]
            end
            state.fourthOpen = f[8] == "1"
            state.tier = tonumber(f[9]) or 0
            state.spell = tonumber(f[10]) or 0
            state.outsideDisplay = tonumber(f[11]) or 0
        end
        Refresh()
    elseif kind == "R" then
        catalog = {}
        archetypeOf = {}
        spellNames = {}
    elseif kind == "C" then
        local tier, archetype, spell = tonumber(f[2]), tonumber(f[3]), tonumber(f[4])
        if tier and archetype and spell then
            catalog[tier] = catalog[tier] or {}
            table.insert(catalog[tier], { archetype = archetype, spell = spell })
            archetypeOf[spell] = archetype
            spellNames[spell] = f[5]
        end
    elseif kind == "K" then
        for i = 1, TIERS do
            choices[i] = tonumber(f[1 + i]) or 0
        end
        if picker:IsShown() then RefreshPicker() end
        Refresh()
    end
end

local events = CreateFrame("Frame")
events:RegisterEvent("CHAT_MSG_ADDON")
events:RegisterEvent("PLAYER_REGEN_DISABLED")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:SetScript("OnEvent", function(_, event, prefix, message, _, sender)
    if event == "CHAT_MSG_ADDON" then
        -- only what the module sends: the player to himself
        if prefix == PREFIX and sender == UnitName("player") then
            OnModuleMessage(message)
        end
    elseif event == "PLAYER_REGEN_DISABLED" then
        picker:Hide()
        Refresh()
    else
        Refresh()
    end
end)

AIO.SavePosition(bar, true)

SLASH_LIMITBREAK1 = "/limitbreak"
SLASH_LIMITBREAK2 = "/limite"
SlashCmdList["LIMITBREAK"] = function()
    if picker:IsShown() then picker:Hide() else OpenPicker() end
end

AIO.Handle("LimitBreak", "Hello")
