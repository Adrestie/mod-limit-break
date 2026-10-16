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
 * mod-limit-break script loader.
 *
 * The function name is imposed by the CMake generation: Add<directory>Scripts,
 * with the dashes of the directory name turned into underscores.
 * mod-limit-break -> Addmod_limit_breakScripts
 */

void AddSC_limit_break_scripts();
void AddSC_limit_break_commandscript();

void Addmod_limit_breakScripts()
{
    AddSC_limit_break_scripts();
    AddSC_limit_break_commandscript();
}
