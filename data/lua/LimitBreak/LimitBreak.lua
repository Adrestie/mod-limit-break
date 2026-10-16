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
    Limit Break, server side (ALE).

    THIS FILE DECIDES NOTHING. It relays the three requests of the bar to the
    module's `.limitbreak` commands, RUN AS THE PLAYER; every rule lives in
    the C++ module, which also sends the bar its state directly (addon
    messages with the prefix "LimitBreak", at a low fixed rate).

    Use carries no parameter on purpose: anyone can call these handlers with
    /run, so the server recomputes everything from the player alone. Choose
    carries a tier and a spell, which the module checks again.
------------------------------------------------------------------------------]]

local AIO = require("AIO")

local Handlers = AIO.AddHandlers("LimitBreak", {})

-- The client says hello once its side is loaded: the catalogue and the
-- choices come back from the module.
function Handlers.Hello(player)
    player:RunCommand("limitbreak catalog")
end

function Handlers.Use(player)
    player:RunCommand("limitbreak use")
end

function Handlers.Choose(player, tier, spell)
    tier, spell = tonumber(tier), tonumber(spell)
    if not tier or not spell then
        return
    end
    tier, spell = math.floor(tier), math.floor(spell)
    if tier < 1 or tier > 4 or spell < 0 or spell > 4294967295 then
        return
    end
    player:RunCommand(string.format("limitbreak choose %d %d", tier, spell))
end
