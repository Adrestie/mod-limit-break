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

    THE BAR: the gauge of the group in segments -- three, and a fourth while a
    boss of the list is engaged -- with one action slot beside it. The slot
    shows the spell of the tier REACHED only; when no spell is chosen for that
    tier, it opens the selection window instead, and is greyed in combat. A
    small button opens the selection at any time out of combat.

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
    title     = FR and "Limite" or "Limit Break",
    tier      = FR and "Palier %d" or "Tier %d",
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
    pickTip   = FR and "Clic : choisir. Clic sur le choix actuel : l'effacer."
                    or "Click: choose. Click the current choice: clear it.",
    boss      = FR and "4e segment : ouvert par un boss" or "4th segment: opened by a boss",
    moveTip   = FR and "Maj + glisser : déplacer la barre" or "Shift + drag: move the bar",
    archetypes = {
        [1] = FR and "Soin" or "Heal",
        [2] = FR and "Dégâts physiques" or "Physical damage",
        [3] = FR and "Dégâts magiques" or "Magic damage",
        [4] = FR and "Tank" or "Tank",
    },
}

local ARCHETYPE_ICONS = {
    [1] = "Interface\\Icons\\Spell_Holy_FlashHeal",
    [2] = "Interface\\Icons\\Ability_MeleeDamage",
    [3] = "Interface\\Icons\\Spell_Fire_FlameBolt",
    [4] = "Interface\\Icons\\Ability_Warrior_DefensiveStance",
}
local CHOOSE_ICON = "Interface\\Icons\\INV_Misc_Book_09"

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

local function SpellLabel(spell)
    local name = GetSpellInfo(spell)
    if name then
        return name
    end
    local archetype = archetypeOf[spell]
    return (archetype and L.archetypes[archetype] or "?") .. " (#" .. spell .. ")"
end

local function SpellIcon(spell)
    local _, _, icon = GetSpellInfo(spell)
    return icon or ARCHETYPE_ICONS[archetypeOf[spell] or 0] or CHOOSE_ICON
end

local function InCombat()
    return InCombatLockdown() or UnitAffectingCombat("player")
end

-- ---------------------------------------------------------------------------
-- The bar
-- ---------------------------------------------------------------------------

local SEG_W, SEG_H, SEG_GAP, SLOT = 60, 14, 3, 36

local bar = CreateFrame("Frame", "LimitBreakBar", UIParent)
bar:SetSize(TIERS * SEG_W + (TIERS - 1) * SEG_GAP + SLOT + 12, SLOT + 18)
bar:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 180)
bar:SetMovable(true)
bar:EnableMouse(true)
bar:RegisterForDrag("LeftButton")
bar:SetScript("OnDragStart", function(self) if IsShiftKeyDown() then self:StartMoving() end end)
bar:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
bar:Hide()

local title = bar:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
title:SetPoint("TOPLEFT", bar, "TOPLEFT", 0, 0)

local segments = {}
for i = 1, TIERS do
    local seg = CreateFrame("StatusBar", nil, bar)
    seg:SetSize(SEG_W, SEG_H)
    seg:SetPoint("BOTTOMLEFT", bar, "BOTTOMLEFT", (i - 1) * (SEG_W + SEG_GAP), (SLOT - SEG_H) / 2)
    seg:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
    seg:SetMinMaxValues(0, 1)
    seg:SetValue(0)
    local bg = seg:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetTexture(0, 0, 0, 0.6)
    local label = seg:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    label:SetPoint("CENTER")
    label:SetText(i)
    seg:EnableMouse(true)
    seg:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_TOP")
        GameTooltip:SetText(L.tier:format(i))
        if i == TIERS then GameTooltip:AddLine(L.boss, 1, 1, 1) end
        GameTooltip:AddLine(L.moveTip, 0.6, 0.6, 0.6)
        GameTooltip:Show()
    end)
    seg:SetScript("OnLeave", function() GameTooltip:Hide() end)
    segments[i] = seg
end

-- The action slot: the spell of the tier reached, or the way to choose one.
local slot = CreateFrame("Button", "LimitBreakSlot", bar)
slot:SetSize(SLOT, SLOT)
slot:SetPoint("BOTTOMRIGHT", bar, "BOTTOMRIGHT", 0, 0)
slot:SetNormalTexture(CHOOSE_ICON)
slot:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
slot:SetPushedTexture("Interface\\Buttons\\UI-Quickslot-Depress")

-- The small button that opens the selection at any time.
local gear = CreateFrame("Button", nil, bar)
gear:SetSize(16, 16)
gear:SetPoint("TOPRIGHT", bar, "TOPRIGHT", 0, 0)
gear:SetNormalTexture(CHOOSE_ICON)
gear:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")

-- ---------------------------------------------------------------------------
-- The selection window
-- ---------------------------------------------------------------------------

local picker = CreateFrame("Frame", "LimitBreakPicker", UIParent)
picker:SetSize(330, 60 + TIERS * 44)
picker:SetPoint("CENTER")
picker:SetBackdrop({
    bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
    edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
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

local pickerTitle = picker:CreateFontString(nil, "OVERLAY", "GameFontNormal")
pickerTitle:SetPoint("TOP", 0, -18)
pickerTitle:SetText(L.choose)

local close = CreateFrame("Button", nil, picker, "UIPanelCloseButton")
close:SetPoint("TOPRIGHT", -6, -6)

local pickerEmpty = picker:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
pickerEmpty:SetPoint("CENTER")
pickerEmpty:SetText(L.empty)

local rows = {}
for tier = 1, TIERS do
    local label = picker:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("TOPLEFT", picker, "TOPLEFT", 22, -48 - (tier - 1) * 44)
    label:SetText(L.tier:format(tier))
    rows[tier] = { label = label, buttons = {} }
end

local function PickerButton(tier, index)
    local row = rows[tier]
    local b = row.buttons[index]
    if b then
        return b
    end
    b = CreateFrame("Button", nil, picker)
    b:SetSize(32, 32)
    b:SetPoint("TOPLEFT", picker, "TOPLEFT", 90 + (index - 1) * 40, -40 - (tier - 1) * 44)
    b:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    b.icon = b:CreateTexture(nil, "ARTWORK")
    b.icon:SetAllPoints()
    b.check = b:CreateTexture(nil, "OVERLAY")
    b.check:SetTexture("Interface\\Buttons\\CheckButtonHilight")
    b.check:SetBlendMode("ADD")
    b.check:SetAllPoints()
    b:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        if GetSpellInfo(self.spell) then
            GameTooltip:SetHyperlink("spell:" .. self.spell)
        else
            GameTooltip:SetText(SpellLabel(self.spell))
        end
        GameTooltip:AddLine(L.archetypes[self.archetype] or "?", 0.6, 0.8, 1)
        GameTooltip:AddLine(L.pickTip, 0.6, 0.6, 0.6)
        GameTooltip:Show()
    end)
    b:SetScript("OnLeave", function() GameTooltip:Hide() end)
    b:SetScript("OnClick", function(self)
        if InCombat() then
            UIErrorsFrame:AddMessage(L.combat, 1, 0.1, 0.1)
            return
        end
        -- clicking the current choice clears it
        local spell = choices[self.tier] == self.spell and 0 or self.spell
        AIO.Handle("LimitBreak", "Choose", self.tier, spell)
    end)
    row.buttons[index] = b
    return b
end

local function RefreshPicker()
    local any = false
    local combat = InCombat()
    for tier = 1, TIERS do
        local entries = catalog[tier] or {}
        for index, entry in ipairs(entries) do
            local b = PickerButton(tier, index)
            b.tier, b.archetype, b.spell = tier, entry.archetype, entry.spell
            b.icon:SetTexture(SpellIcon(entry.spell))
            b.icon:SetDesaturated(combat)
            if choices[tier] == entry.spell then b.check:Show() else b.check:Hide() end
            b:Show()
            any = true
        end
        for index = #entries + 1, #rows[tier].buttons do
            rows[tier].buttons[index]:Hide()
        end
    end
    if any then pickerEmpty:Hide() else pickerEmpty:Show() end
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
    bar:SetAlpha(live and 1 or 0.45)
    if state.hud == HUD_PAUSED then
        title:SetText(L.title .. " - " .. L.paused)
    elseif state.hud == HUD_OUTSIDE then
        title:SetText(L.title .. " - " .. L.outside)
    else
        title:SetText(L.title)
    end

    -- each segment fills between its threshold and the previous one
    local low = 0
    for i = 1, TIERS do
        local high = state.thresholds[i] or low
        local seg = segments[i]
        local fill = high > low and (state.points - low) / (high - low) or 0
        seg:SetValue(math.max(0, math.min(1, fill)))
        if fill >= 1 then
            seg:SetStatusBarColor(1, 0.75, 0.1)
        else
            seg:SetStatusBarColor(0.2, 0.55, 1)
        end
        low = high
    end
    if state.fourthOpen then
        segments[TIERS]:SetAlpha(1)
    else
        segments[TIERS]:SetAlpha(0.25)
        segments[TIERS]:SetValue(0)
    end

    -- the slot: the spell of the tier reached, or the way to choose one
    local combat = InCombat()
    if live and state.tier > 0 and state.spell > 0 then
        slot:SetNormalTexture(SpellIcon(state.spell))
        slot:GetNormalTexture():SetDesaturated(false)
        slot:Enable()
        slot.mode = "use"
    elseif live and state.tier > 0 then
        slot:SetNormalTexture(CHOOSE_ICON)
        slot:GetNormalTexture():SetDesaturated(combat)
        if combat then slot:Disable() else slot:Enable() end
        slot.mode = "choose"
    else
        slot:SetNormalTexture(CHOOSE_ICON)
        slot:GetNormalTexture():SetDesaturated(true)
        slot:Disable()
        slot.mode = nil
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
        GameTooltip:SetText(SpellLabel(state.spell))
        GameTooltip:AddLine(L.useTip:format(state.tier), 1, 1, 1, true)
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
    elseif kind == "C" then
        local tier, archetype, spell = tonumber(f[2]), tonumber(f[3]), tonumber(f[4])
        if tier and archetype and spell then
            catalog[tier] = catalog[tier] or {}
            table.insert(catalog[tier], { archetype = archetype, spell = spell })
            archetypeOf[spell] = archetype
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
