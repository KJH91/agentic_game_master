import json
import os
import re
import time
from copy import deepcopy
from datetime import datetime

from map_system import init_map, add_location

SAVES_DIR = "/saves"

RACE_STAT_BONUSES = {
    "Human":    {"strength": 1, "dexterity": 1, "constitution": 1, "intelligence": 1, "wisdom": 1, "charisma": 1},
    "Elf":      {"dexterity": 2, "intelligence": 1},
    "Dwarf":    {"constitution": 2, "wisdom": 1},
    "Halfling": {"dexterity": 2, "charisma": 1},
    "Half-Orc": {"strength": 2, "constitution": 1},
    # Sci-Fi / Cyberpunk equivalents
    "Android":  {"intelligence": 2, "dexterity": 1},
    "Mutant":   {"constitution": 2, "strength": 1},
    "Alien":    {"wisdom": 2, "charisma": 1},
    "Human (Augmented)": {"dexterity": 1, "intelligence": 1, "constitution": 1},
}

CLASS_DEFINITIONS = {
    "Warrior": {
        "health": 44,
        "mana": 0,
        "base_stats": {"strength": 16, "dexterity": 12, "constitution": 14, "intelligence": 8, "wisdom": 10, "charisma": 11},
        "starting_items": [
            {"name": "Longsword", "type": "weapon", "damage": "1d8", "description": "A sturdy iron longsword"},
            {"name": "Leather Armour", "type": "armour", "ac_bonus": 2, "description": "Basic leather armour"},
            {"name": "Health Potion", "type": "consumable", "quantity": 2, "description": "Restores 2d4+2 health"},
        ],
        "equipped": {"weapon": "Longsword", "armour": "Leather Armour"},
        "gold": 15,
        "health_per_level": 8,
        "description": "A master of martial combat, tough and deadly in close quarters.",
        "playstyle": "High damage, heavy armour, front-line fighter",
        "ac": 14,
    },
    "Mage": {
        "health": 24,
        "mana": 30,
        "base_stats": {"strength": 8, "dexterity": 12, "constitution": 10, "intelligence": 17, "wisdom": 13, "charisma": 12},
        "starting_items": [
            {"name": "Arcane Staff", "type": "weapon", "damage": "1d6", "description": "A gnarled wooden staff humming with power"},
            {"name": "Robes", "type": "armour", "ac_bonus": 0, "description": "Simple but magically reinforced robes"},
            {"name": "Mana Potion", "type": "consumable", "quantity": 2, "description": "Restores 2d4+2 mana"},
            {"name": "Spellbook", "type": "misc", "description": "Contains your known spells"},
        ],
        "equipped": {"weapon": "Arcane Staff", "armour": "Robes"},
        "gold": 10,
        "health_per_level": 4,
        "description": "A wielder of arcane forces, devastating from range but fragile.",
        "playstyle": "Powerful spells, low health, high intelligence",
        "ac": 10,
    },
    "Rogue": {
        "health": 30,
        "mana": 0,
        "base_stats": {"strength": 10, "dexterity": 17, "constitution": 12, "intelligence": 13, "wisdom": 11, "charisma": 14},
        "starting_items": [
            {"name": "Daggers (pair)", "type": "weapon", "damage": "1d4", "description": "Twin balanced throwing daggers"},
            {"name": "Leather Armour", "type": "armour", "ac_bonus": 2, "description": "Supple leather armour for quiet movement"},
            {"name": "Thieves' Tools", "type": "misc", "description": "Lock picks and tools of the trade"},
            {"name": "Health Potion", "type": "consumable", "quantity": 1, "description": "Restores 2d4+2 health"},
        ],
        "equipped": {"weapon": "Daggers (pair)", "armour": "Leather Armour"},
        "gold": 20,
        "health_per_level": 6,
        "description": "A shadow operative skilled in stealth, trickery, and precision strikes.",
        "playstyle": "Sneak attacks, evasion, social manipulation",
        "ac": 13,
    },
    "Ranger": {
        "health": 34,
        "mana": 0,
        "base_stats": {"strength": 12, "dexterity": 16, "constitution": 13, "intelligence": 11, "wisdom": 14, "charisma": 10},
        "starting_items": [
            {"name": "Shortbow", "type": "weapon", "damage": "1d6", "description": "A well-crafted shortbow with a quiver of 20 arrows"},
            {"name": "Hunting Knife", "type": "weapon", "damage": "1d4", "description": "A sharp hunting knife"},
            {"name": "Studded Leather", "type": "armour", "ac_bonus": 3, "description": "Leather reinforced with metal studs"},
            {"name": "Health Potion", "type": "consumable", "quantity": 1, "description": "Restores 2d4+2 health"},
        ],
        "equipped": {"weapon": "Shortbow", "armour": "Studded Leather"},
        "gold": 12,
        "health_per_level": 6,
        "description": "A wilderness expert deadly at range, companion to beasts.",
        "playstyle": "Ranged combat, tracking, nature magic",
        "ac": 13,
    },
    "Cleric": {
        "health": 36,
        "mana": 20,
        "base_stats": {"strength": 13, "dexterity": 10, "constitution": 13, "intelligence": 10, "wisdom": 16, "charisma": 13},
        "starting_items": [
            {"name": "Mace", "type": "weapon", "damage": "1d6", "description": "A heavy iron mace bearing your deity's symbol"},
            {"name": "Chain Shirt", "type": "armour", "ac_bonus": 3, "description": "Interlocked rings of iron"},
            {"name": "Holy Symbol", "type": "misc", "description": "Your sacred focus for divine magic"},
            {"name": "Health Potion", "type": "consumable", "quantity": 2, "description": "Restores 2d4+2 health"},
        ],
        "equipped": {"weapon": "Mace", "armour": "Chain Shirt"},
        "gold": 10,
        "health_per_level": 6,
        "description": "A divine champion channelling the power of their deity.",
        "playstyle": "Healing, divine magic, tanky support",
        "ac": 13,
    },
    "Paladin": {
        "health": 40,
        "mana": 10,
        "base_stats": {"strength": 15, "dexterity": 10, "constitution": 14, "intelligence": 9, "wisdom": 12, "charisma": 15},
        "starting_items": [
            {"name": "Longsword", "type": "weapon", "damage": "1d8", "description": "A holy blade blessed by your deity"},
            {"name": "Scale Mail", "type": "armour", "ac_bonus": 4, "description": "Overlapping metal scales providing strong protection"},
            {"name": "Holy Symbol", "type": "misc", "description": "Your sacred focus"},
            {"name": "Health Potion", "type": "consumable", "quantity": 1, "description": "Restores 2d4+2 health"},
        ],
        "equipped": {"weapon": "Longsword", "armour": "Scale Mail"},
        "gold": 8,
        "health_per_level": 7,
        "description": "A holy warrior combining martial prowess with divine smite.",
        "playstyle": "Heavy hitter, divine buffs, inspire allies",
        "ac": 16,
    },
    # Sci-Fi / Cyberpunk classes
    "Soldier": {
        "health": 44,
        "mana": 0,
        "base_stats": {"strength": 16, "dexterity": 13, "constitution": 14, "intelligence": 9, "wisdom": 11, "charisma": 10},
        "starting_items": [
            {"name": "Assault Rifle", "type": "weapon", "damage": "2d6", "description": "Standard-issue combat rifle"},
            {"name": "Combat Armour", "type": "armour", "ac_bonus": 4, "description": "Military-grade ballistic vest"},
            {"name": "Medkit", "type": "consumable", "quantity": 2, "description": "Restores 2d6+2 health"},
        ],
        "equipped": {"weapon": "Assault Rifle", "armour": "Combat Armour"},
        "gold": 200,
        "health_per_level": 8,
        "description": "A battle-hardened combatant specialising in firearms and tactics.",
        "playstyle": "High firepower, tactical positioning",
        "ac": 14,
    },
    "Hacker": {
        "health": 24,
        "mana": 30,
        "base_stats": {"strength": 8, "dexterity": 13, "constitution": 10, "intelligence": 17, "wisdom": 12, "charisma": 12},
        "starting_items": [
            {"name": "Pistol", "type": "weapon", "damage": "1d8", "description": "A compact sidearm"},
            {"name": "Hacking Deck", "type": "misc", "description": "Military-grade cyberspace interface"},
            {"name": "Medkit", "type": "consumable", "quantity": 1, "description": "Restores 2d6+2 health"},
        ],
        "equipped": {"weapon": "Pistol", "armour": "None"},
        "gold": 150,
        "health_per_level": 4,
        "description": "A digital ghost who owns the net and controls machines.",
        "playstyle": "System intrusion, drone control, intelligence gathering",
        "ac": 10,
    },
}

SETTING_RACES = {
    "High Fantasy":     ["Human", "Elf", "Dwarf", "Halfling", "Half-Orc"],
    "Dark Fantasy":     ["Human", "Elf", "Dwarf", "Halfling", "Half-Orc"],
    "Sci-Fi":           ["Human (Augmented)", "Android", "Alien", "Mutant"],
    "Post-Apocalyptic": ["Human", "Mutant", "Half-Orc"],
    "Cyberpunk":        ["Human (Augmented)", "Android", "Mutant"],
}

SETTING_CLASSES = {
    "High Fantasy":     ["Warrior", "Mage", "Rogue", "Ranger", "Cleric", "Paladin"],
    "Dark Fantasy":     ["Warrior", "Mage", "Rogue", "Ranger", "Cleric", "Paladin"],
    "Sci-Fi":           ["Soldier", "Hacker", "Ranger"],
    "Post-Apocalyptic": ["Warrior", "Rogue", "Ranger", "Soldier"],
    "Cyberpunk":        ["Soldier", "Hacker", "Rogue"],
}

XP_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500, 5500]


def create_initial_state(name: str, race: str, class_name: str, setting: str, difficulty: str, background: str = "") -> dict:
    class_def = CLASS_DEFINITIONS[class_name]
    stats = deepcopy(class_def["base_stats"])

    bonuses = RACE_STAT_BONUSES.get(race, {})
    for stat, bonus in bonuses.items():
        stats[stat] = stats.get(stat, 10) + bonus

    difficulty_multiplier = {"Story Mode": 1.25, "Standard": 1.0, "Hardcore": 0.75}
    health_mult = difficulty_multiplier.get(difficulty, 1.0)
    max_health = int(class_def["health"] * health_mult)

    return {
        "player": {
            "name": name,
            "race": race,
            "class": class_name,
            "background": background,
            "level": 1,
            "experience": 0,
            "experience_to_next": XP_THRESHOLDS[1],
            "health": max_health,
            "max_health": max_health,
            "mana": class_def["mana"],
            "max_mana": class_def["mana"],
            "stats": stats,
            "inventory": deepcopy(class_def["starting_items"]),
            "gold": class_def["gold"],
            "equipped": deepcopy(class_def["equipped"]),
            "ac": class_def["ac"],
            "proficiency_bonus": 2,
            "abilities": [],
        },
        "world": {
            "setting": setting,
            "current_location": "Unknown",
            "locations_visited": [],
            "time_of_day": "Morning",
            "weather": "Clear",
        },
        "quests": {
            "active": [],
            "completed": [],
        },
        "npcs_met": [],
        "combat": {
            "in_combat": False,
            "enemies": [],
            "round": 0,
            "initiative_order": [],
        },
        "story_flags": {},
        "difficulty": difficulty,
        "map": init_map(),
        "conversation_history": [],
        "summary_history": [],
    }


def apply_state_update(game_state: dict, update_text: str) -> tuple[dict, list[str]]:
    """Parse and apply a [STATE_UPDATE] block. Returns updated state and list of change notices."""
    state = deepcopy(game_state)
    notices = []

    block_match = re.search(r"\[STATE_UPDATE\](.*?)\[/STATE_UPDATE\]", update_text, re.DOTALL)
    if not block_match:
        return state, notices

    block = block_match.group(1).strip()

    def _parse_value(raw: str):
        raw = raw.strip()
        try:
            return json.loads(raw)
        except Exception:
            if raw.lower() == "true":
                return True
            if raw.lower() == "false":
                return False
            try:
                return int(raw)
            except Exception:
                return raw

    lines = block.split("\n")
    parsed = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if ":" in line:
            key, _, rest = line.partition(":")
            key = key.strip()
            rest = rest.strip()
            # Check if value spans multiple lines (JSON object/array)
            if rest.startswith("{") or rest.startswith("["):
                json_buf = rest
                while i + 1 < len(lines) and not _is_complete_json(json_buf):
                    i += 1
                    json_buf += "\n" + lines[i]
                parsed[key] = _parse_value(json_buf)
            else:
                parsed[key] = _parse_value(rest)
        i += 1

    player = state["player"]

    if "xp_gained" in parsed:
        xp = int(parsed["xp_gained"])
        player["experience"] += xp
        notices.append(f"✨ Gained {xp} XP!")

    if "health_change" in parsed:
        change = int(parsed["health_change"])
        player["health"] = max(0, min(player["max_health"], player["health"] + change))
        if change < 0:
            notices.append(f"💔 Lost {abs(change)} HP ({player['health']}/{player['max_health']})")
        else:
            notices.append(f"💚 Healed {change} HP ({player['health']}/{player['max_health']})")

    if "mana_change" in parsed:
        change = int(parsed["mana_change"])
        player["mana"] = max(0, min(player["max_mana"], player["mana"] + change))

    if "gold_gained" in parsed:
        player["gold"] += int(parsed["gold_gained"])
        notices.append(f"💰 Gained {parsed['gold_gained']} gold")

    if "gold_lost" in parsed:
        player["gold"] = max(0, player["gold"] - int(parsed["gold_lost"]))

    if "items_found" in parsed:
        items = parsed["items_found"] if isinstance(parsed["items_found"], list) else [parsed["items_found"]]
        for item in items:
            if isinstance(item, dict):
                player["inventory"].append(item)
                notices.append(f"🎒 Found: {item['name']}")

    if "items_lost" in parsed:
        lost = parsed["items_lost"] if isinstance(parsed["items_lost"], list) else [parsed["items_lost"]]
        for item_name in lost:
            player["inventory"] = [i for i in player["inventory"] if i.get("name") != item_name]

    if "quest_completed" in parsed:
        quest_id = str(parsed["quest_completed"])
        active = state["quests"]["active"]
        completed = next((q for q in active if q.get("id") == quest_id), None)
        if completed:
            active.remove(completed)
            state["quests"]["completed"].append(completed)
            notices.append(f"✅ Quest completed: {completed['title']}")

    if "quest_added" in parsed:
        quest = parsed["quest_added"]
        if isinstance(quest, dict):
            state["quests"]["active"].append(quest)
            notices.append(f"📜 New quest: {quest.get('title', 'Unknown')}")

    if "location_changed" in parsed:
        loc = str(parsed["location_changed"])
        prev_loc = state["world"].get("current_location")
        state["world"]["current_location"] = loc
        if loc not in state["world"]["locations_visited"]:
            state["world"]["locations_visited"].append(loc)
        state["map"] = add_location(state.get("map", init_map()), loc, prev_loc)

    if "time_changed" in parsed:
        state["world"]["time_of_day"] = str(parsed["time_changed"])

    if "npc_met" in parsed:
        npc = parsed["npc_met"]
        if isinstance(npc, dict):
            existing = next((n for n in state["npcs_met"] if n.get("name") == npc.get("name")), None)
            if existing:
                existing.update(npc)
            else:
                state["npcs_met"].append(npc)

    if "story_flag" in parsed:
        flag = parsed["story_flag"]
        if isinstance(flag, dict):
            state["story_flags"][flag["key"]] = flag["value"]

    return state, notices


def _is_complete_json(s: str) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


def check_level_up(game_state: dict) -> tuple[dict, bool]:
    state = deepcopy(game_state)
    player = state["player"]
    current_level = player["level"]

    if current_level >= len(XP_THRESHOLDS):
        return state, False

    if player["experience"] >= player["experience_to_next"]:
        new_level = current_level + 1
        player["level"] = new_level

        class_name = player["class"]
        class_def = CLASS_DEFINITIONS.get(class_name, {})
        hp_gain = class_def.get("health_per_level", 6)
        player["max_health"] += hp_gain
        player["health"] = player["max_health"]

        if new_level < len(XP_THRESHOLDS):
            player["experience_to_next"] = XP_THRESHOLDS[new_level]
        else:
            player["experience_to_next"] = XP_THRESHOLDS[-1] + (new_level - len(XP_THRESHOLDS) + 1) * 1000

        player["proficiency_bonus"] = 2 + ((new_level - 1) // 4)

        return state, True

    return state, False


def strip_state_update(text: str) -> str:
    return re.sub(r"\[STATE_UPDATE\].*?\[/STATE_UPDATE\]", "", text, flags=re.DOTALL).strip()


def add_to_history(game_state: dict, role: str, content: str) -> dict:
    state = deepcopy(game_state)
    state["conversation_history"].append({"role": role, "content": content})

    if len(state["conversation_history"]) > 30:
        # Keep last 20 exchanges, archive older ones as a note
        state["conversation_history"] = state["conversation_history"][-20:]

    return state


def save_game(game_state: dict) -> str:
    os.makedirs(SAVES_DIR, exist_ok=True)
    char_name = game_state["player"]["name"].replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{char_name}_{timestamp}.json"
    path = os.path.join(SAVES_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(game_state, f, indent=2, ensure_ascii=False)
    return path


def load_game(filename: str) -> dict:
    path = os.path.join(SAVES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saves() -> list[dict]:
    os.makedirs(SAVES_DIR, exist_ok=True)
    saves = []
    for fname in sorted(os.listdir(SAVES_DIR), reverse=True):
        if fname.endswith(".json"):
            path = os.path.join(SAVES_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                player = state.get("player", {})
                saves.append({
                    "filename": fname,
                    "display": f"{player.get('name', '?')} — {player.get('class', '?')} Lv.{player.get('level', 1)} | {state.get('world', {}).get('current_location', '?')} | {fname[:-5].split('_')[-2]}",
                    "state": state,
                })
            except Exception:
                pass
    return saves
