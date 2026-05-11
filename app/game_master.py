from __future__ import annotations

import re
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from dice import roll, roll_attack, roll_damage, roll_initiative, stat_modifier, format_roll_display
from prompts import build_system_prompt, build_opening_prompt, LEVEL_UP_PROMPT
from game_state import apply_state_update, strip_state_update, check_level_up, add_to_history

OLLAMA_BASE_URL = "http://host.docker.internal:11434"
MODEL_NAME = "llama3.2"


def _build_llm() -> ChatOllama:
    return ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        temperature=0.85,
        num_predict=1024,
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


def process_player_action(game_state: dict, player_input: str, campaign_context: str | None = None) -> tuple[dict, str, list[str], str | None]:
    """
    Process a player action. Returns (updated_state, narrative, notices, dice_display).
    dice_display is a formatted string of any dice rolls performed, or None.
    """
    llm = _build_llm()
    state = game_state

    dice_display = None
    augmented_input = player_input

    # If in combat, pre-resolve dice for the player's action
    if state["combat"]["in_combat"]:
        dice_display, augmented_input = _resolve_combat_dice(state, player_input)

    state = add_to_history(state, "user", player_input)

    system_msg = SystemMessage(content=build_system_prompt(state, campaign_context))
    history_msgs = _history_to_messages(state["conversation_history"][:-1])  # exclude the one we just added

    if dice_display:
        action_content = f"{player_input}\n\n[DICE RESULTS - narrate around these exact outcomes]\n{dice_display}"
    else:
        action_content = player_input

    messages = [system_msg] + history_msgs + [HumanMessage(content=action_content)]

    response = llm.invoke(messages)
    raw_text = response.content

    state, notices = apply_state_update(state, raw_text)
    narrative = strip_state_update(raw_text)

    state = add_to_history(state, "assistant", narrative)

    # Check for level up
    state, levelled_up = check_level_up(state)
    if levelled_up:
        level_narrative = _generate_level_up_narrative(state, llm)
        notices.append(f"🎉 LEVEL UP! You are now level {state['player']['level']}!")
        narrative = narrative + "\n\n---\n\n" + level_narrative

    return state, narrative, notices, dice_display


def _resolve_combat_dice(game_state: dict, player_input: str) -> tuple[str, str]:
    """Pre-roll dice for combat actions based on player input."""
    player = game_state["player"]
    stats = player["stats"]
    lines = []

    action_lower = player_input.lower()
    is_attack = any(w in action_lower for w in ["attack", "strike", "hit", "slash", "stab", "shoot", "fire", "smite"])
    is_spell = any(w in action_lower for w in ["cast", "spell", "magic", "fireball", "lightning", "heal", "blast"])
    is_flee = any(w in action_lower for w in ["flee", "run", "escape", "retreat"])

    if is_attack:
        weapon = player["equipped"].get("weapon", "")
        weapon_item = next((i for i in player["inventory"] if i.get("name") == weapon), None)
        damage_dice = weapon_item.get("damage", "1d6") if weapon_item else "1d6"

        str_mod = stat_modifier(stats["strength"])
        dex_mod = stat_modifier(stats["dexterity"])
        attack_mod = max(str_mod, dex_mod) if "bow" in weapon.lower() or "dagger" in weapon.lower() else str_mod
        prof = player.get("proficiency_bonus", 2)

        atk = roll_attack(attack_mod, prof)
        lines.append(f"🎲 Attack Roll: 1d20+{attack_mod + prof} = [{atk['roll']}]+{attack_mod + prof} = {atk['total']}")

        # Roll damage regardless — GM narrates hit/miss
        dmg = roll_damage(damage_dice, attack_mod)
        lines.append(f"⚔️ Damage: {damage_dice}+{attack_mod} = {dmg['total']}")

    elif is_spell and player.get("mana", 0) > 0:
        int_mod = stat_modifier(stats["intelligence"])
        wis_mod = stat_modifier(stats["wisdom"])
        spell_mod = max(int_mod, wis_mod)
        atk = roll("1d20")
        lines.append(f"🔮 Spell Attack: 1d20+{spell_mod} = [{atk['rolls'][0]}]+{spell_mod} = {atk['total'] + spell_mod}")
        dmg = roll("2d6")
        lines.append(f"✨ Spell Damage: 2d6 = {dmg['total']}")

    elif is_flee:
        dex_mod = stat_modifier(stats["dexterity"])
        flee_roll = roll("1d20")
        lines.append(f"🏃 Flee Check: 1d20+{dex_mod} = [{flee_roll['rolls'][0]}]+{dex_mod} = {flee_roll['total'] + dex_mod}")

    return "\n".join(lines) if lines else None, player_input


def _generate_level_up_narrative(game_state: dict, llm: ChatOllama) -> str:
    prompt = LEVEL_UP_PROMPT.format(new_level=game_state["player"]["level"])
    messages = [
        SystemMessage(content=build_system_prompt(game_state)),
        HumanMessage(content=prompt),
    ]
    response = llm.invoke(messages)
    return strip_state_update(response.content)


def start_combat(game_state: dict, enemies: list[dict]) -> tuple[dict, str]:
    """
    Initialise combat state with enemy list. Returns (updated_state, initiative_display).
    Each enemy: {"name": str, "health": int, "max_health": int, "ac": int, "damage": str, "attack_bonus": int}
    """
    import copy
    state = copy.deepcopy(game_state)
    player = state["player"]

    dex_mod = stat_modifier(player["stats"]["dexterity"])
    player_init = roll_initiative(dex_mod)

    initiative_order = [{"name": player["name"], "initiative": player_init, "is_player": True}]

    for enemy in enemies:
        enemy_init = roll_initiative(0)
        enemy["initiative"] = enemy_init
        initiative_order.append({"name": enemy["name"], "initiative": enemy_init, "is_player": False})

    initiative_order.sort(key=lambda x: x["initiative"], reverse=True)

    state["combat"] = {
        "in_combat": True,
        "enemies": enemies,
        "round": 1,
        "initiative_order": initiative_order,
    }

    display_lines = ["⚔️ **COMBAT BEGINS!** ⚔️", "", "**Initiative Order:**"]
    for i, entry in enumerate(initiative_order):
        marker = "→" if i == 0 else "  "
        display_lines.append(f"{marker} {entry['name']}: {entry['initiative']}")

    return state, "\n".join(display_lines)


def end_combat(game_state: dict) -> dict:
    import copy
    state = copy.deepcopy(game_state)
    state["combat"] = {
        "in_combat": False,
        "enemies": [],
        "round": 0,
        "initiative_order": [],
    }
    return state
