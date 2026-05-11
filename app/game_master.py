from __future__ import annotations

import json
import re
from copy import deepcopy
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from dice import roll, roll_attack, roll_damage, roll_initiative, stat_modifier
from prompts import build_system_prompt, build_opening_prompt, build_combat_narration_prompt, LEVEL_UP_PROMPT
from game_state import apply_state_update, strip_state_update, check_level_up, add_to_history

OLLAMA_BASE_URL = "http://host.docker.internal:11434"
MODEL_NAME = "llama3.2"

# Words that suggest enemies are present — used as fallback when LLM omits combat_start
_COMBAT_SIGNALS = {
    "attack", "attacked", "attacks", "charge", "charges", "fight", "fights",
    "battle", "enemy", "enemies", "foe", "foes", "hostile", "ambush",
    "lunge", "lunges", "lunging", "draws their", "raises their weapon",
    "goblin", "orc", "bandit", "guard", "soldier", "creature", "monster",
    "warrior", "combatant", "threatens", "aims at you", "fires at you",
    "revenant", "cultist", "raider", "mercenary", "drone", "android",
}


def _build_llm(temperature: float = 0.85, num_predict: int = 1024) -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        num_predict=num_predict,
    )


def _history_to_messages(conversation_history: list[dict]) -> list:
    messages = []
    for entry in conversation_history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role == "assistant":
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def get_opening_scene(game_state: dict, campaign_context: str | None = None) -> tuple[dict, str, list[str]]:
    """Generate the opening scene for a new game. Returns (updated_state, narrative, notices)."""
    llm = _build_llm()
    opening_prompt = build_opening_prompt(game_state)
    messages = [
        SystemMessage(content=build_system_prompt(game_state, campaign_context)),
        HumanMessage(content=opening_prompt),
    ]
    response = llm.invoke(messages)
    raw_text = response.content
    state, notices = apply_state_update(game_state, raw_text)
    narrative = strip_state_update(raw_text)
    state = add_to_history(state, "assistant", narrative)
    return state, narrative, notices


def process_player_action(
    game_state: dict,
    player_input: str,
    campaign_context: str | None = None,
) -> tuple[dict, str, list[str], str | None]:
    """
    Process a player action. Returns (updated_state, narrative, notices, dice_display).

    In combat: Python resolves every roll before calling the LLM, which only narrates.
    Out of combat: LLM drives story; combat_start STATE_UPDATE triggers combat setup.
    If the LLM forgets combat_start, a fallback extraction step detects enemies and starts combat.
    """
    llm = _build_llm()
    state = game_state
    dice_display: str | None = None
    narrative = ""
    notices: list[str] = []

    if state["combat"]["in_combat"]:
        # ── Combat path: Python is sole authority on all rolls ────────────────
        state, dice_lines, outcomes = resolve_combat_round(state, player_input)
        dice_display = "\n".join(dice_lines) if dice_lines else None

        state = add_to_history(state, "user", player_input)
        narration_prompt = build_combat_narration_prompt(state, player_input, outcomes)
        messages = [
            SystemMessage(content=build_system_prompt(state, campaign_context)),
            HumanMessage(content=narration_prompt),
        ]
        response = llm.invoke(messages)
        raw_text = response.content
        # Only apply STATE_UPDATE for loot / XP / quests — HP is already resolved
        state, notices = apply_state_update(state, raw_text)
        narrative = strip_state_update(raw_text)
        state = add_to_history(state, "assistant", narrative)

    else:
        # ── Story path: LLM drives narrative, may signal combat via STATE_UPDATE ─
        state = add_to_history(state, "user", player_input)
        system_msg = SystemMessage(content=build_system_prompt(state, campaign_context))
        history_msgs = _history_to_messages(state["conversation_history"][:-1])
        messages = [system_msg] + history_msgs + [HumanMessage(content=player_input)]

        response = llm.invoke(messages)
        raw_text = response.content
        state, notices = apply_state_update(state, raw_text)
        narrative = strip_state_update(raw_text)
        state = add_to_history(state, "assistant", narrative)

        # Fallback: if LLM omitted combat_start but the narrative clearly describes enemies
        if not state["combat"]["in_combat"] and _narrative_signals_combat(narrative):
            enemies = _extract_enemies(narrative, state, llm)
            if enemies:
                trigger = f"[STATE_UPDATE]\ncombat_start: {json.dumps(enemies)}\n[/STATE_UPDATE]"
                state, combat_notices = apply_state_update(state, trigger)
                notices.extend(combat_notices)

    # Level up (both paths)
    state, levelled_up = check_level_up(state)
    if levelled_up:
        level_narrative = _generate_level_up_narrative(state, llm)
        notices.append(f"🎉 LEVEL UP! You are now level {state['player']['level']}!")
        narrative = narrative + "\n\n---\n\n" + level_narrative

    return state, narrative, notices, dice_display


# ── Combat resolution ─────────────────────────────────────────────────────────

def resolve_combat_round(
    game_state: dict,
    player_input: str,
) -> tuple[dict, list[str], list[str]]:
    """
    Fully resolve one turn-based combat round: player action then all living enemies attack.
    Python is sole authority on every roll. Returns (updated_state, dice_lines, outcome_sentences).
    dice_lines use HTML <b> tags so they render correctly inside the UI's HTML dice-display div.
    """
    state = deepcopy(game_state)
    player = state["player"]
    combat = state["combat"]
    dice_lines: list[str] = []
    outcomes: list[str] = []

    action_lower = player_input.lower()
    is_attack = any(w in action_lower for w in [
        "attack", "strike", "hit", "slash", "stab", "shoot", "fire",
        "smite", "swing", "charge", "fight",
    ])
    is_spell = any(w in action_lower for w in [
        "cast", "spell", "magic", "fireball", "lightning", "blast", "arcane",
    ])
    is_flee = any(w in action_lower for w in [
        "flee", "run", "escape", "retreat", "back away",
    ])

    living = [e for e in combat["enemies"] if e.get("health", 0) > 0]

    # ── Player turn ───────────────────────────────────────────────────────────
    if is_flee:
        state, dice_lines, outcomes = _resolve_flee(state, dice_lines, outcomes)
    elif is_spell and player.get("mana", 0) > 0 and living:
        state, dice_lines, outcomes = _resolve_player_spell(state, living[0], dice_lines, outcomes)
    elif living:
        state, dice_lines, outcomes = _resolve_player_attack(state, living[0], dice_lines, outcomes)
    else:
        outcomes.append("There are no enemies left to fight.")

    # ── Enemy turns (automatic) — only if still in combat and player alive ────
    if state["combat"]["in_combat"] and state["player"]["health"] > 0:
        still_living = [e for e in state["combat"]["enemies"] if e.get("health", 0) > 0]
        for enemy in still_living:
            state, dice_lines, outcomes = _resolve_enemy_attack(state, enemy, dice_lines, outcomes)
            if state["player"]["health"] <= 0:
                break

    # End combat if all enemies are down
    if all(e.get("health", 0) <= 0 for e in state["combat"]["enemies"]):
        state["combat"]["in_combat"] = False
        outcomes.append("All enemies have been defeated!")

    state["combat"]["round"] = combat.get("round", 1) + 1
    return state, dice_lines, outcomes


def _resolve_player_attack(
    state: dict, target: dict, dice_lines: list, outcomes: list
) -> tuple[dict, list, list]:
    player = state["player"]
    stats = player["stats"]
    weapon_name = player["equipped"].get("weapon", "")
    weapon_item = next((i for i in player["inventory"] if i.get("name") == weapon_name), None)
    damage_dice = weapon_item.get("damage", "1d6") if weapon_item else "1d6"

    str_mod = stat_modifier(stats["strength"])
    dex_mod = stat_modifier(stats["dexterity"])
    finesse = any(w in weapon_name.lower() for w in ["bow", "dagger", "rapier", "pistol", "rifle"])
    attack_mod = max(str_mod, dex_mod) if finesse else str_mod
    prof = player.get("proficiency_bonus", 2)
    total_bonus = attack_mod + prof

    atk = roll_attack(attack_mod, prof)
    hit = atk["total"] >= target["ac"]
    dice_lines.append(
        f"🎲 Your Attack: 1d20+{total_bonus} = [{atk['roll']}]+{total_bonus} = "
        f"<b>{atk['total']}</b> vs AC {target['ac']} — {'<b>HIT</b>' if hit else '<b>MISS</b>'}"
    )

    if hit:
        dmg_result = roll_damage(damage_dice, attack_mod)
        dmg = max(1, dmg_result["total"])
        target["health"] = max(0, target["health"] - dmg)
        dice_lines.append(
            f"⚔️ Damage: {damage_dice}+{attack_mod} = <b>{dmg}</b> damage dealt"
        )
        if target["health"] <= 0:
            outcomes.append(f"You strike {target['name']} for {dmg} damage, killing it.")
        else:
            outcomes.append(
                f"You hit {target['name']} for {dmg} damage "
                f"({target['health']}/{target.get('max_health', target['health'])} HP remaining)."
            )
    else:
        outcomes.append(
            f"You swing at {target['name']} but miss. (Roll {atk['total']} vs AC {target['ac']})"
        )

    return state, dice_lines, outcomes


def _resolve_player_spell(
    state: dict, target: dict, dice_lines: list, outcomes: list
) -> tuple[dict, list, list]:
    player = state["player"]
    stats = player["stats"]
    int_mod = stat_modifier(stats["intelligence"])
    wis_mod = stat_modifier(stats["wisdom"])
    spell_mod = max(int_mod, wis_mod)
    prof = player.get("proficiency_bonus", 2)
    total_bonus = spell_mod + prof

    atk_roll = roll("1d20")
    raw_roll = atk_roll["rolls"][0]
    total_attack = raw_roll + total_bonus
    hit = total_attack >= target["ac"]

    player["mana"] = max(0, player["mana"] - 5)
    dice_lines.append(
        f"🔮 Spell Attack: 1d20+{total_bonus} = [{raw_roll}]+{total_bonus} = "
        f"<b>{total_attack}</b> vs AC {target['ac']} — {'<b>HIT</b>' if hit else '<b>MISS</b>'}"
    )

    if hit:
        dmg_result = roll("2d6")
        dmg = max(1, dmg_result["total"] + spell_mod)
        target["health"] = max(0, target["health"] - dmg)
        dice_lines.append(f"✨ Spell Damage: 2d6+{spell_mod} = <b>{dmg}</b> damage dealt")
        if target["health"] <= 0:
            outcomes.append(f"Your spell blasts {target['name']} for {dmg} damage, destroying it.")
        else:
            outcomes.append(
                f"Your spell strikes {target['name']} for {dmg} damage "
                f"({target['health']}/{target.get('max_health', target['health'])} HP remaining)."
            )
    else:
        outcomes.append(
            f"Your spell fizzles and misses {target['name']}. "
            f"(Roll {total_attack} vs AC {target['ac']})"
        )

    return state, dice_lines, outcomes


def _resolve_flee(
    state: dict, dice_lines: list, outcomes: list
) -> tuple[dict, list, list]:
    player = state["player"]
    dex_mod = stat_modifier(player["stats"]["dexterity"])
    result = roll("1d20")
    raw = result["rolls"][0]
    total = raw + dex_mod
    dc = 10

    success = total >= dc
    dice_lines.append(
        f"🏃 Flee Check: 1d20+{dex_mod} = [{raw}]+{dex_mod} = "
        f"<b>{total}</b> vs DC {dc} — {'<b>SUCCESS</b>' if success else '<b>FAILED</b>'}"
    )

    if success:
        state["combat"]["in_combat"] = False
        outcomes.append(f"You successfully break away and flee the battle! (Roll: {total} vs DC {dc})")
    else:
        outcomes.append(f"You fail to escape — the enemies block your way! (Roll: {total} vs DC {dc})")

    return state, dice_lines, outcomes


def _resolve_enemy_attack(
    state: dict, enemy: dict, dice_lines: list, outcomes: list
) -> tuple[dict, list, list]:
    player = state["player"]
    player_ac = player.get("ac", 10)
    atk_bonus = enemy.get("attack_bonus", 2)
    dmg_dice = enemy.get("damage", "1d6")

    atk_roll = roll("1d20")
    raw = atk_roll["rolls"][0]
    total = raw + atk_bonus
    hit = total >= player_ac

    dice_lines.append(
        f"🎲 {enemy['name']} attacks: 1d20+{atk_bonus} = [{raw}]+{atk_bonus} = "
        f"<b>{total}</b> vs your AC {player_ac} — {'<b>HIT</b>' if hit else '<b>MISS</b>'}"
    )

    if hit:
        dmg_result = roll(dmg_dice)
        dmg = max(1, dmg_result["total"])
        player["health"] = max(0, player["health"] - dmg)
        dice_lines.append(
            f"💔 {enemy['name']} deals <b>{dmg}</b> damage  "
            f"(Your HP: <b>{player['health']}</b>/{player['max_health']})"
        )
        if player["health"] <= 0:
            outcomes.append(f"{enemy['name']} strikes you for {dmg} damage. You collapse to the ground!")
        else:
            outcomes.append(
                f"{enemy['name']} hits you for {dmg} damage "
                f"({player['health']}/{player['max_health']} HP remaining)."
            )
    else:
        outcomes.append(
            f"{enemy['name']}'s attack misses you. (Roll {total} vs your AC {player_ac})"
        )

    return state, dice_lines, outcomes


# ── Enemy detection / extraction ──────────────────────────────────────────────

def _narrative_signals_combat(text: str) -> bool:
    """Return True if at least two combat-related words appear in the text."""
    lower = text.lower()
    return sum(1 for signal in _COMBAT_SIGNALS if signal in lower) >= 2


def _extract_enemies(narrative: str, game_state: dict, llm: ChatOllama) -> list[dict]:
    """
    Ask the LLM to extract enemy stats from a narrative that signals combat.
    Uses a low-temperature, short-response call with a JSON-only prompt.
    Falls back to a level-appropriate default if parsing fails.
    """
    player = game_state["player"]
    level = player["level"]
    setting = game_state.get("world", {}).get("setting", "High Fantasy")

    prompt = (
        f"The player (Level {level} {player['class']}) is about to fight enemies described here:\n\n"
        f'"{narrative[:500]}"\n\n'
        "Output ONLY a JSON array with their combat stats — no explanation, nothing else:\n"
        '[{"name": "Enemy Name", "health": 15, "max_health": 15, '
        '"ac": 12, "damage": "1d6", "attack_bonus": 2}]'
    )

    extraction_llm = _build_llm(temperature=0.1, num_predict=300)
    try:
        resp = extraction_llm.invoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
        match = re.search(r'\[.+\]', text, re.DOTALL)
        if match:
            enemies = json.loads(match.group(0))
            if isinstance(enemies, list) and enemies and all(isinstance(e, dict) for e in enemies):
                for e in enemies:
                    e.setdefault("max_health", e.get("health", 10))
                    e.setdefault("ac", 12)
                    e.setdefault("damage", "1d6")
                    e.setdefault("attack_bonus", 2)
                return enemies
    except Exception:
        pass

    return [_default_enemy(level, setting)]


def _default_enemy(level: int, setting: str) -> dict:
    hp = max(8, level * 6)
    ac = max(11, 10 + level // 2)
    atk = max(2, level)
    dmg_sides = min(12, 4 + (level - 1) * 2)

    name_map = {
        "Sci-Fi":           ["Security Drone", "Gang Enforcer", "Combat Android"],
        "Cyberpunk":        ["Street Mercenary", "Corp Guard", "Combat Android"],
        "Post-Apocalyptic": ["Raider", "Mutant", "Warlord's Soldier"],
        "Dark Fantasy":     ["Revenant", "Cultist", "Death Knight"],
    }
    names = name_map.get(setting, ["Goblin Raider", "Bandit", "Orc Warrior"])
    name = names[min(level - 1, len(names) - 1)]
    return {
        "name": name,
        "health": hp,
        "max_health": hp,
        "ac": ac,
        "damage": f"1d{dmg_sides}",
        "attack_bonus": atk,
    }


def _generate_level_up_narrative(game_state: dict, llm: ChatOllama) -> str:
    prompt = LEVEL_UP_PROMPT.format(new_level=game_state["player"]["level"])
    messages = [
        SystemMessage(content=build_system_prompt(game_state)),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    return strip_state_update(response.content)
