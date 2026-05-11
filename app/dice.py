import random
import re


def roll(dice_notation: str) -> dict:
    """Parse and roll dice notation like '1d20', '2d6', '1d8+3'."""
    pattern = r"(\d+)d(\d+)([+-]\d+)?"
    match = re.match(pattern, dice_notation.strip().lower().replace(" ", ""))
    if not match:
        raise ValueError(f"Invalid dice notation: {dice_notation}")

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    return {
        "notation": dice_notation,
        "rolls": rolls,
        "modifier": modifier,
        "total": total,
    }


def roll_initiative(dexterity_modifier: int) -> int:
    result = roll("1d20")
    return result["total"] + dexterity_modifier


def roll_attack(strength_modifier: int, proficiency_bonus: int) -> dict:
    result = roll("1d20")
    attack_total = result["total"] + strength_modifier + proficiency_bonus
    return {
        "roll": result["rolls"][0],
        "modifier": strength_modifier + proficiency_bonus,
        "total": attack_total,
        "notation": f"1d20+{strength_modifier + proficiency_bonus}",
    }


def roll_damage(damage_dice: str, modifier: int = 0) -> dict:
    result = roll(damage_dice)
    total = result["total"] + modifier
    return {
        "notation": damage_dice,
        "rolls": result["rolls"],
        "modifier": modifier,
        "total": total,
    }


def stat_modifier(stat_value: int) -> int:
    return (stat_value - 10) // 2


def format_roll_display(label: str, roll_result: dict, target_ac: int = None) -> str:
    rolls_str = "+".join(str(r) for r in roll_result["rolls"])
    mod_str = f" + {roll_result['modifier']}" if roll_result["modifier"] > 0 else (f" - {abs(roll_result['modifier'])}" if roll_result["modifier"] < 0 else "")
    line = f"🎲 {label}: {roll_result['notation']} = [{rolls_str}]{mod_str} = {roll_result['total']}"
    if target_ac is not None:
        outcome = "HIT!" if roll_result["total"] >= target_ac else "MISS"
        line += f" vs AC {target_ac} → {outcome}"
    return line
