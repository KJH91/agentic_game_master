import base64
import json
import os
import streamlit as st
import streamlit.components.v1 as components

from game_state import (
    create_initial_state,
    save_game,
    load_game,
    list_saves,
    SETTING_RACES,
    SETTING_CLASSES,
    CLASS_DEFINITIONS,
    RACE_STAT_BONUSES,
    XP_THRESHOLDS,
)
from game_master import get_opening_scene, process_player_action
from map_system import render_map_png
from tts_engine import synthesize, VOICES, DEFAULT_VOICE
from image_generator import generate as generate_image, is_available as sd_available, is_loading as sd_loading
from campaign_loader import from_pdf as load_pdf, from_text as load_text
import multiplayer as mp

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Game Master",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;1,400&display=swap');

.stApp { background-color: #0d0d0d; color: #e8d5b0; }

.gm-message {
    background: linear-gradient(135deg, #1a1209 0%, #231810 100%);
    border: 1px solid #5a3e1b;
    border-left: 4px solid #c4902a;
    border-radius: 4px;
    padding: 1rem 1.2rem;
    margin: 0.5rem 0;
    font-family: 'Crimson Text', Georgia, serif;
    font-size: 1.05rem;
    line-height: 1.75;
    color: #e8d5b0;
}
.player-message {
    background: #0f1a2a;
    border: 1px solid #1e3a5f;
    border-right: 4px solid #4a9eff;
    border-radius: 4px;
    padding: 0.6rem 1rem;
    margin: 0.5rem 0;
    text-align: right;
    color: #9ec8ff;
    font-style: italic;
}
.mp-player-message {
    background: #0f1a2a;
    border-right: 4px solid var(--pc);
    border-radius: 4px;
    padding: 0.6rem 1rem;
    margin: 0.5rem 0;
    color: #cce;
    font-style: italic;
}
.dice-display {
    background: #0a1a0a;
    border: 1px solid #2d5a1e;
    border-radius: 4px;
    padding: 0.5rem 1rem;
    margin: 0.3rem 0;
    font-family: 'Courier New', monospace;
    font-size: 0.88rem;
    color: #7dff7d;
}
.notice-box {
    background: #1a1a00;
    border: 1px solid #5a5a00;
    border-radius: 4px;
    padding: 0.35rem 0.8rem;
    margin: 0.2rem 0;
    font-size: 0.88rem;
    color: #ffee88;
}
.level-up-banner {
    background: linear-gradient(135deg, #1a1a00, #2a2a00);
    border: 2px solid #ffd700;
    border-radius: 8px;
    padding: 0.8rem;
    text-align: center;
    color: #ffd700;
    font-size: 1.2rem;
    margin: 0.5rem 0;
}
.game-title {
    font-family: 'Crimson Text', Georgia, serif;
    font-size: 2.2rem;
    color: #c4902a;
    text-shadow: 0 0 20px rgba(196,144,42,0.4);
    margin-bottom: 0;
}
.setting-badge {
    display: inline-block;
    background: #2a1a00;
    border: 1px solid #c4902a;
    border-radius: 12px;
    padding: 2px 12px;
    font-size: 0.78rem;
    color: #c4902a;
}
.session-code {
    font-family: monospace;
    font-size: 2rem;
    letter-spacing: 0.3em;
    color: #ffd700;
    background: #111;
    border: 2px solid #5a4a00;
    border-radius: 8px;
    padding: 0.5rem 1rem;
    text-align: center;
    display: block;
    margin: 0.5rem auto;
}
</style>
""", unsafe_allow_html=True)

# ── Persistent settings ───────────────────────────────────────────────────────
_SETTINGS_FILE = "/saves/settings.json"
_SETTINGS_KEYS = ["voice_enabled", "voice_name", "sound_enabled", "image_enabled"]


def _load_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings():
    os.makedirs("/saves", exist_ok=True)
    data = {k: st.session_state.get(k) for k in _SETTINGS_KEYS}
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


# ── Session state ─────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "screen":               "main_menu",
        "creation_step":        1,
        "creation_data":        {},
        "game_state":           None,
        "chat_log":             [],
        "waiting_for_response": False,
        # Feature flags (defaults — overridden by saved settings below)
        "voice_enabled":        False,
        "voice_name":           list(VOICES.keys())[0],
        "sound_enabled":        True,
        "image_enabled":        False,
        # Pending audio / image
        "pending_audio":        None,
        "pending_sound":        None,
        # Campaign
        "campaign_context":     None,
        # Multiplayer
        "mp_active":            False,
        "mp_session_id":        None,
        "mp_player_id":         None,
        "mp_player_name":       None,
        "mp_last_ts":           0.0,
    }

    # Overlay persisted settings so they survive page refreshes
    saved = _load_settings()
    for k in _SETTINGS_KEYS:
        if k in saved:
            defaults[k] = saved[k]

    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ── Sound effects (Web Audio API, synthesised in-browser) ─────────────────────
_SOUND_JS = {
    "combat": """
        const C=new AudioContext();
        [[110,0],[90,0.3],[70,0.55]].forEach(([f,t])=>{
            const o=C.createOscillator(),g=C.createGain();
            o.type='sawtooth';o.frequency.value=f;
            g.gain.setValueAtTime(0.18,C.currentTime+t);
            g.gain.exponentialRampToValueAtTime(0.001,C.currentTime+t+0.35);
            o.connect(g);g.connect(C.destination);
            o.start(C.currentTime+t);o.stop(C.currentTime+t+0.35);
        });
    """,
    "levelup": """
        const C=new AudioContext();
        [261.63,329.63,392,523.25].forEach((f,i)=>{
            const o=C.createOscillator(),g=C.createGain();
            o.type='sine';o.frequency.value=f;
            g.gain.setValueAtTime(0.22,C.currentTime+i*0.18);
            g.gain.exponentialRampToValueAtTime(0.001,C.currentTime+i*0.18+0.45);
            o.connect(g);g.connect(C.destination);
            o.start(C.currentTime+i*0.18);o.stop(C.currentTime+i*0.18+0.45);
        });
    """,
    "item": """
        const C=new AudioContext();
        [523.25,659.25,783.99].forEach((f,i)=>{
            const o=C.createOscillator(),g=C.createGain();
            o.type='sine';o.frequency.value=f;
            g.gain.setValueAtTime(0.18,C.currentTime+i*0.1);
            g.gain.exponentialRampToValueAtTime(0.001,C.currentTime+i*0.1+0.28);
            o.connect(g);g.connect(C.destination);
            o.start(C.currentTime+i*0.1);o.stop(C.currentTime+i*0.1+0.28);
        });
    """,
    "quest": """
        const C=new AudioContext();
        [392,523.25,659.25,523.25,659.25].forEach((f,i)=>{
            const o=C.createOscillator(),g=C.createGain();
            o.type='triangle';o.frequency.value=f;
            g.gain.setValueAtTime(0.18,C.currentTime+i*0.14);
            g.gain.exponentialRampToValueAtTime(0.001,C.currentTime+i*0.14+0.22);
            o.connect(g);g.connect(C.destination);
            o.start(C.currentTime+i*0.14);o.stop(C.currentTime+i*0.14+0.22);
        });
    """,
    "death": """
        const C=new AudioContext();
        [220,196,174.61,146.83].forEach((f,i)=>{
            const o=C.createOscillator(),g=C.createGain();
            o.type='sine';o.frequency.value=f;
            g.gain.setValueAtTime(0.2,C.currentTime+i*0.3);
            g.gain.exponentialRampToValueAtTime(0.001,C.currentTime+i*0.3+0.45);
            o.connect(g);g.connect(C.destination);
            o.start(C.currentTime+i*0.3);o.stop(C.currentTime+i*0.3+0.45);
        });
    """,
}


def _play_sound(sound_type: str):
    js = _SOUND_JS.get(sound_type, "")
    if js:
        components.html(f"<script>{js}</script>", height=1)


# ── Helpers ───────────────────────────────────────────────────────────────────
def push(msg_type: str, text: str, **kw):
    entry = {"type": msg_type, "text": text}
    entry.update(kw)
    st.session_state.chat_log.append(entry)


def _abbr(name: str) -> str:
    return name[:3].upper()


def _mod_str(v: int) -> str:
    m = (v - 10) // 2
    return f"+{m}" if m >= 0 else str(m)


def _xp_pct(state: dict) -> float:
    p = state["player"]
    lvl = p["level"]
    xp, xp_to = p["experience"], p["experience_to_next"]
    prev = XP_THRESHOLDS[lvl - 1] if lvl <= len(XP_THRESHOLDS) else 0
    return min(1.0, (xp - prev) / max(1, xp_to - prev))


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    state = st.session_state.game_state
    if not state:
        return

    player = state["player"]
    world  = state.get("world", {})

    with st.sidebar:
        st.markdown(f"### {player['name']}")
        st.caption(f"{player['race']} {player['class']} · Lv {player['level']}")

        if st.session_state.mp_active:
            sid = st.session_state.mp_session_id
            st.markdown(f'<span class="setting-badge">👥 Session: {sid}</span>', unsafe_allow_html=True)

        st.divider()

        # Vitals
        hp_pct = player["health"] / max(player["max_health"], 1)
        st.markdown(f"**❤️ HP** {player['health']}/{player['max_health']}")
        st.progress(hp_pct)

        if player.get("max_mana", 0) > 0:
            mp_pct = player["mana"] / max(player["max_mana"], 1)
            st.markdown(f"**💙 MP** {player['mana']}/{player['max_mana']}")
            st.progress(mp_pct)

        st.markdown(f"**✨ XP** {player['experience']}/{player['experience_to_next']}")
        st.progress(_xp_pct(state))
        st.markdown(f"**💰 {player['gold']} gold**")
        st.divider()

        # Stats
        st.markdown("**Stats**")
        stats = player["stats"]
        cols = st.columns(3)
        for i, (stat, val) in enumerate(stats.items()):
            cols[i % 3].metric(_abbr(stat), val, _mod_str(val), delta_color="off")

        st.divider()

        # Equipped
        equipped = player.get("equipped", {})
        equipped_items = {k: v for k, v in equipped.items() if v and v.lower() != "none"}
        if equipped_items:
            st.markdown("**Equipped**")
            for slot, item in equipped_items.items():
                st.caption(f"*{slot.title()}:* {item}")

        # Inventory
        with st.expander(f"🎒 Inventory ({len(player['inventory'])})"):
            for item in player["inventory"]:
                qty = f" ×{item['quantity']}" if "quantity" in item else ""
                st.markdown(f"**{item['name']}**{qty}")
                if "description" in item:
                    st.caption(item["description"])

        st.divider()

        # Quests
        active_q = state["quests"]["active"]
        done_q   = state["quests"]["completed"]
        with st.expander(f"📜 Quests ({len(active_q)} active)"):
            for quest in active_q:
                st.markdown(f"**{quest['title']}**")
                for obj in quest.get("objectives", []):
                    done = obj in quest.get("completed_objectives", [])
                    st.caption(f"{'✅' if done else '◻️'} {obj}")
            if done_q:
                st.caption("— Completed —")
                for quest in done_q:
                    st.caption(f"~~{quest['title']}~~")

        st.divider()

        # Map
        map_img = render_map_png(state)
        if map_img:
            with st.expander("🗺️ World Map", expanded=len(state.get("map", {}).get("nodes", {})) > 1):
                st.image(map_img, use_container_width=True)

        # Combat enemies
        if state["combat"]["in_combat"]:
            st.divider()
            st.markdown("**⚔️ Enemies**")
            for enemy in state["combat"]["enemies"]:
                hp = enemy.get("health", 0)
                max_hp = enemy.get("max_health", hp)
                if hp > 0:
                    st.markdown(f"**{enemy['name']}**")
                    st.progress(hp / max(max_hp, 1), text=f"{hp}/{max_hp} HP")
                else:
                    st.caption(f"~~{enemy['name']}~~ ☠️")

        st.divider()

        # Location / time
        st.caption(f"📍 {world.get('current_location', 'Unknown')}")
        st.caption(f"🕐 {world.get('time_of_day', '')} · {world.get('weather', '')}")

        st.divider()

        # Settings
        with st.expander("⚙️ Settings"):
            st.session_state.voice_enabled = st.toggle(
                "🔊 GM Voice (edge-tts)", value=st.session_state.voice_enabled)
            if st.session_state.voice_enabled:
                st.session_state.voice_name = st.selectbox(
                    "Voice", list(VOICES.keys()),
                    index=list(VOICES.keys()).index(st.session_state.voice_name))
            st.session_state.sound_enabled = st.toggle(
                "🎵 Sound Effects", value=st.session_state.sound_enabled)
            st.session_state.image_enabled = st.toggle(
                "🖼️ Scene Images (Stable Diffusion)", value=st.session_state.image_enabled)
            if st.session_state.image_enabled:
                if sd_available():
                    st.success("Stable Diffusion ready ✓")
                elif sd_loading():
                    st.info("⏳ Model loading — images available shortly")
                else:
                    st.warning("SD container not reachable")
            _save_settings()

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save", use_container_width=True):
                save_game(st.session_state.game_state)
                st.success("Saved!")
        with col2:
            if st.button("🏠 Menu", use_container_width=True):
                _go_menu()


def _go_menu():
    st.session_state.screen = "main_menu"
    st.session_state.game_state = None
    st.session_state.chat_log = []
    st.session_state.mp_active = False
    st.session_state.mp_session_id = None
    st.session_state.mp_player_id = None
    st.session_state.campaign_context = None
    st.rerun()


# ── Main menu ─────────────────────────────────────────────────────────────────
def screen_main_menu():
    st.markdown('<p class="game-title">⚔️ AI Game Master</p>', unsafe_allow_html=True)
    st.markdown("*An adaptive AI-powered tabletop RPG experience — running entirely on your machine*")
    st.divider()

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🗡️ New Game", use_container_width=True, type="primary"):
            st.session_state.screen = "character_creation"
            st.session_state.creation_step = 1
            st.session_state.creation_data = {}
            st.session_state.campaign_context = None
            st.rerun()

        if st.button("📂 Load Game", use_container_width=True):
            st.session_state.screen = "load_game"
            st.rerun()

        if st.button("👥 Multiplayer", use_container_width=True):
            st.session_state.screen = "multiplayer_lobby"
            st.rerun()

        st.divider()
        st.markdown("""
**Requirements:**
- Ollama running locally with `llama3.2` pulled
- Docker Desktop

**Optional extras:**
- Stable Diffusion (AUTOMATIC1111) on port 7860 for scene images
- Internet connection for GM voice (edge-tts)
""")


# ── Load game ─────────────────────────────────────────────────────────────────
def screen_load_game():
    st.markdown("## Load Game")
    saves = list_saves()

    if not saves:
        st.info("No save files found.")
        if st.button("← Back"):
            st.session_state.screen = "main_menu"
            st.rerun()
        return

    for s in saves:
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(f"**{s['display']}**")
        with c2:
            if st.button("Load", key=f"load_{s['filename']}"):
                st.session_state.game_state = s["state"]
                st.session_state.chat_log = []
                for entry in s["state"].get("conversation_history", []):
                    t = "gm" if entry["role"] == "assistant" else "player"
                    st.session_state.chat_log.append({"type": t, "text": entry["content"]})
                st.session_state.screen = "game"
                st.rerun()

    if st.button("← Back"):
        st.session_state.screen = "main_menu"
        st.rerun()


# ── Multiplayer lobby ─────────────────────────────────────────────────────────
def screen_multiplayer_lobby():
    st.markdown("## 👥 Multiplayer")
    st.markdown("Share a session code with friends. All players see the same world — any player can act.")
    st.divider()

    tab_host, tab_join = st.tabs(["Host a Session", "Join a Session"])

    with tab_host:
        st.markdown("### Host New Session")
        st.info("Create a new world, then share the session code with other players.")
        host_name = st.text_input("Your player name", key="host_name", placeholder="e.g. Aldric")
        if host_name and st.button("Create Session & Start Character Creation", type="primary"):
            st.session_state.mp_player_name = host_name
            st.session_state.mp_active = True
            st.session_state.screen = "character_creation"
            st.session_state.creation_step = 1
            st.session_state.creation_data = {}
            st.rerun()

    with tab_join:
        st.markdown("### Join Existing Session")
        active = mp.list_sessions()
        if active:
            st.markdown("**Active sessions:**")
            for sess in active:
                players_str = ", ".join(sess["players"])
                st.caption(f"`{sess['session_id']}` — {sess['setting']} · {sess['location']} · Players: {players_str}")

        join_code = st.text_input("Session Code", key="join_code",
                                   placeholder="6-character code from the host").upper().strip()
        join_name = st.text_input("Your player name", key="join_name", placeholder="e.g. Lyra")

        if join_code and join_name and st.button("Join Session", type="primary"):
            pid, state = mp.join_session(join_code, join_name)
            if state is None:
                st.error("Session not found. Check the code and try again.")
            else:
                st.session_state.game_state = state
                st.session_state.mp_active = True
                st.session_state.mp_session_id = join_code
                st.session_state.mp_player_id = pid
                st.session_state.mp_player_name = join_name
                st.session_state.mp_last_ts = state["multiplayer"]["last_updated"]
                # Rebuild chat log
                st.session_state.chat_log = []
                for entry in state.get("conversation_history", []):
                    t = "gm" if entry["role"] == "assistant" else "player"
                    st.session_state.chat_log.append({"type": t, "text": entry["content"]})
                st.session_state.screen = "game"
                st.rerun()

    if st.button("← Back"):
        st.session_state.screen = "main_menu"
        st.rerun()


# ── Character creation ────────────────────────────────────────────────────────
SETTINGS = ["High Fantasy", "Dark Fantasy", "Sci-Fi", "Post-Apocalyptic", "Cyberpunk"]
SETTING_DESCRIPTIONS = {
    "High Fantasy":     "Swords, sorcery, ancient dragons and forgotten kingdoms",
    "Dark Fantasy":     "Grim horror, morally grey choices, bleak and dangerous world",
    "Sci-Fi":           "Space exploration, alien worlds, advanced technology",
    "Post-Apocalyptic": "Survival in a ruined world, scarce resources, desperate factions",
    "Cyberpunk":        "Megacities, corporate warfare, hacking, and neon streets",
}
DIFFICULTIES = {
    "Story Mode":  "Easier enemies — focus on narrative and exploration",
    "Standard":    "Balanced challenge — the intended experience",
    "Hardcore":    "Permadeath, tough enemies, unforgiving consequences",
}


def screen_character_creation():
    step = st.session_state.creation_step
    data = st.session_state.creation_data

    st.markdown(f"## Character Creation — Step {step} of 5")
    st.progress(step / 5)
    st.divider()

    if step == 1:
        st.markdown("### Choose Your Campaign Setting")

        # Campaign PDF upload
        with st.expander("📖 Or upload a premade campaign PDF (optional)"):
            uploaded = st.file_uploader("Campaign PDF", type=["pdf"], key="campaign_pdf")
            campaign_text_input = st.text_area(
                "Or paste campaign text directly",
                placeholder="Paste your campaign notes, adventure module, or world description here...",
                height=100, key="campaign_text_input")

            if uploaded:
                campaign = load_pdf(uploaded)
                st.session_state.campaign_context = campaign
                st.success(f"Campaign loaded — {len(campaign)} characters extracted.")
            elif campaign_text_input:
                st.session_state.campaign_context = load_text(campaign_text_input)
                st.info("Campaign text stored.")
            elif st.session_state.campaign_context:
                st.info("Campaign loaded from earlier upload.")

        st.markdown("---")

        for s in SETTINGS:
            selected = data.get("setting") == s
            label = f"{'✅ ' if selected else ''}{s}"
            if st.button(f"**{label}** — {SETTING_DESCRIPTIONS[s]}", key=f"set_{s}",
                         use_container_width=True):
                data["setting"] = s
                st.session_state.creation_data = data

        if "setting" in data:
            if st.button("Next →", type="primary"):
                st.session_state.creation_step = 2
                st.rerun()

    elif step == 2:
        setting = data["setting"]
        races = SETTING_RACES.get(setting, ["Human"])
        st.markdown("### Choose Your Race / Species")
        for race in races:
            bonuses = RACE_STAT_BONUSES.get(race, {})
            bonus_str = ", ".join(f"+{v} {k[:3].title()}" for k, v in bonuses.items()) or "Balanced"
            if st.button(f"**{race}** — {bonus_str}", key=f"race_{race}", use_container_width=True):
                data["race"] = race
                st.session_state.creation_data = data

        if "race" in data:
            bonuses = RACE_STAT_BONUSES.get(data["race"], {})
            if bonuses:
                st.success(f"**{data['race']}:** " + ", ".join(f"+{v} {k.title()}" for k, v in bonuses.items()))

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back"): st.session_state.creation_step = 1; st.rerun()
        with c2:
            if "race" in data and st.button("Next →", type="primary"):
                st.session_state.creation_step = 3; st.rerun()

    elif step == 3:
        setting = data["setting"]
        classes = SETTING_CLASSES.get(setting, list(CLASS_DEFINITIONS.keys()))
        st.markdown("### Choose Your Class")
        for cls in classes:
            d = CLASS_DEFINITIONS.get(cls, {})
            if st.button(f"**{cls}** — {d.get('description', '')}", key=f"cls_{cls}",
                         use_container_width=True):
                data["class"] = cls
                st.session_state.creation_data = data

        if "class" in data:
            d = CLASS_DEFINITIONS.get(data["class"], {})
            c1, c2, c3 = st.columns(3)
            c1.metric("❤️ HP", d.get("health", "?"))
            c2.metric("💙 MP", d.get("mana", 0))
            c3.metric("🛡️ AC", d.get("ac", 10))
            st.info(f"**Playstyle:** {d.get('playstyle', '')}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back"): st.session_state.creation_step = 2; st.rerun()
        with c2:
            if "class" in data and st.button("Next →", type="primary"):
                st.session_state.creation_step = 4; st.rerun()

    elif step == 4:
        st.markdown("### Name Your Character")
        name = st.text_input("Character Name", value=data.get("name", ""),
                             placeholder="Enter your character's name...")
        background = st.text_area(
            "Backstory (optional — leave blank for the GM to craft it)",
            value=data.get("background", ""), height=120)

        if name:   data["name"] = name
        if background: data["background"] = background

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back"): st.session_state.creation_step = 3; st.rerun()
        with c2:
            if name and st.button("Next →", type="primary"):
                st.session_state.creation_data = data
                st.session_state.creation_step = 5; st.rerun()

    elif step == 5:
        st.markdown("### Choose Difficulty")
        for diff, desc in DIFFICULTIES.items():
            selected = data.get("difficulty") == diff
            label = f"{'✅ ' if selected else ''}{diff}"
            if st.button(f"**{label}** — {desc}", key=f"diff_{diff}", use_container_width=True):
                data["difficulty"] = diff
                st.session_state.creation_data = data

        if "difficulty" in data:
            st.divider()
            st.markdown("### Your Character")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Name:** {data.get('name', '?')}")
                st.markdown(f"**Race:** {data.get('race', '?')}")
                st.markdown(f"**Class:** {data.get('class', '?')}")
            with c2:
                st.markdown(f"**Setting:** {data.get('setting', '?')}")
                st.markdown(f"**Difficulty:** {data.get('difficulty', '?')}")
                if st.session_state.campaign_context:
                    st.markdown("**Campaign:** Custom PDF ✓")

            cls_def = CLASS_DEFINITIONS.get(data.get("class", ""), {})
            if cls_def:
                st.markdown("**Starting Stats:**")
                stats   = cls_def.get("base_stats", {})
                bonuses = RACE_STAT_BONUSES.get(data.get("race", ""), {})
                cols = st.columns(6)
                for i, (stat, val) in enumerate(stats.items()):
                    cols[i].metric(_abbr(stat), val + bonuses.get(stat, 0))

        c1, c2 = st.columns(2)
        with c1:
            if st.button("← Back"): st.session_state.creation_step = 4; st.rerun()
        with c2:
            if "difficulty" in data and st.button("⚔️ Begin Adventure!", type="primary"):
                _start_new_game(data)


# ── Game start ────────────────────────────────────────────────────────────────
def _start_new_game(data: dict):
    with st.spinner("The Game Master prepares your world..."):
        game_state = create_initial_state(
            name=data["name"],
            race=data["race"],
            class_name=data["class"],
            setting=data["setting"],
            difficulty=data["difficulty"],
            background=data.get("background", ""),
        )
        campaign = st.session_state.campaign_context
        game_state, opening, notices = get_opening_scene(game_state, campaign_context=campaign)

    st.session_state.chat_log = []
    for notice in notices:
        push("notice", notice)
    push("gm", opening)

    # Multiplayer: create a session if hosting
    if st.session_state.mp_active and not st.session_state.mp_session_id:
        host_name = st.session_state.mp_player_name or data["name"]
        sid, pid, game_state = mp.create_session(game_state, host_name)
        st.session_state.mp_session_id = sid
        st.session_state.mp_player_id  = pid
        st.session_state.mp_last_ts    = game_state["multiplayer"]["last_updated"]

    st.session_state.game_state = game_state

    # Optional voice for opening scene
    if st.session_state.voice_enabled:
        voice = VOICES.get(st.session_state.voice_name, DEFAULT_VOICE)
        audio = synthesize(opening, voice)
        st.session_state.pending_audio = audio

    st.session_state.screen = "game"
    st.rerun()


# ── Game screen ───────────────────────────────────────────────────────────────
def screen_game():
    render_sidebar()

    state  = st.session_state.game_state
    player = state["player"]
    world  = state.get("world", {})

    # ── Header ────────────────────────────────────────────────────────────────
    c_title, c_badge = st.columns([3, 1])
    with c_title:
        st.markdown(f'<p class="game-title">⚔️ {player["name"]}\'s Adventure</p>',
                    unsafe_allow_html=True)
    with c_badge:
        st.markdown(f'<span class="setting-badge">{world.get("setting","")}</span>',
                    unsafe_allow_html=True)

    if state["combat"]["in_combat"]:
        combat = state["combat"]
        living_enemies = [e for e in combat["enemies"] if e.get("health", 0) > 0]
        st.error(f"⚔️ **COMBAT — Round {combat['round']}**", icon="⚔️")
        cols = st.columns(len(living_enemies)) if living_enemies else []
        for col, enemy in zip(cols, living_enemies):
            hp = enemy["health"]
            max_hp = enemy.get("max_health", hp)
            col.markdown(f"**{enemy['name']}**")
            col.progress(hp / max(max_hp, 1), text=f"{hp}/{max_hp} HP")
        st.caption("⚔️ Attack · 🔮 Cast a spell · 🏃 Flee — type your action below")

    if st.session_state.mp_active:
        players = state.get("multiplayer", {}).get("players", [])
        party_str = " · ".join(
            f'<span style="color:{p["color"]}">{p["name"]}</span>' for p in players)
        st.markdown(f"**Party:** {party_str}", unsafe_allow_html=True)

    st.divider()

    # ── Input area (always at top, always visible) ────────────────────────────
    if st.session_state.waiting_for_response:
        st.info("The Game Master is weaving your fate...")
    else:
        with st.form("action_form", clear_on_submit=True):
            player_input = st.text_input(
                "What do you do?", placeholder="Describe your action...",
                label_visibility="collapsed")
            c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
            submitted    = c1.form_submit_button("⚔️ Take Action", type="primary", use_container_width=True)
            save_clicked = c2.form_submit_button("💾 Save", use_container_width=True)
            abandon      = c3.form_submit_button("🏠 Abandon", use_container_width=True)
            if st.session_state.mp_active:
                refresh = c4.form_submit_button("🔄 Refresh", use_container_width=True)
            else:
                refresh = False

        if submitted and player_input.strip():
            _handle_action(player_input.strip())
        if save_clicked:
            save_game(st.session_state.game_state)
            st.success("Game saved!")
        if abandon:
            _go_menu()
        if refresh:
            _mp_sync()

    # Pending audio (voice) — placed just below input so it plays immediately
    if st.session_state.pending_audio:
        st.audio(st.session_state.pending_audio, format="audio/mp3", autoplay=True)
        st.session_state.pending_audio = None

    # Pending sound effect
    if st.session_state.pending_sound and st.session_state.sound_enabled:
        _play_sound(st.session_state.pending_sound)
        st.session_state.pending_sound = None

    st.divider()

    # ── Chat log — newest first ───────────────────────────────────────────────
    for i, msg in enumerate(reversed(st.session_state.chat_log)):
        t    = msg["type"]
        text = msg["text"]

        if t == "gm":
            st.markdown(f'<div class="gm-message">{text.replace(chr(10),"<br>")}</div>',
                        unsafe_allow_html=True)
            # TTS replay button — right-aligned under the message
            _, btn_col = st.columns([9, 1])
            if btn_col.button("▶ Play", key=f"tts_{i}", use_container_width=True,
                              help="Read this message aloud"):
                voice = VOICES.get(st.session_state.voice_name, DEFAULT_VOICE)
                with st.spinner("Generating audio..."):
                    audio = synthesize(text, voice)
                if audio:
                    st.session_state.pending_audio = audio
                    st.rerun()
                else:
                    st.warning("Could not generate audio — check your internet connection.")
        elif t == "player":
            player_label = msg.get("player_name", "")
            display = f"🗣️ {player_label}: {text}" if player_label else f"🗣️ {text}"
            style = f'style="border-right-color:{msg.get("player_color","#4a9eff")}"' if msg.get("player_color") else ""
            st.markdown(f'<div class="player-message" {style}>{display}</div>',
                        unsafe_allow_html=True)
        elif t == "dice":
            st.markdown(f'<div class="dice-display">{text.replace(chr(10),"<br>")}</div>',
                        unsafe_allow_html=True)
        elif t == "notice":
            st.markdown(f'<div class="notice-box">{text.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        elif t == "level_up":
            st.markdown(f'<div class="level-up-banner">🎉 {text} 🎉</div>', unsafe_allow_html=True)
        elif t == "image":
            try:
                img_bytes = base64.b64decode(msg["text"])
                st.image(img_bytes, use_container_width=True)
            except Exception:
                pass


def _handle_action(player_input: str):
    # Identify sender in multiplayer
    if st.session_state.mp_active:
        pname = st.session_state.mp_player_name or ""
        pcolor = ""
        state = st.session_state.game_state
        pid = st.session_state.mp_player_id
        if pid:
            p = mp.get_player(state, pid)
            pname  = p.get("name", pname)
            pcolor = p.get("color", "")
        push("player", player_input, player_name=pname, player_color=pcolor)
    else:
        push("player", player_input)

    st.session_state.waiting_for_response = True
    st.rerun()


def _process_pending_action():
    state = st.session_state.game_state
    last_player = next(
        (m["text"] for m in reversed(st.session_state.chat_log) if m["type"] == "player"),
        None)

    if not last_player:
        st.session_state.waiting_for_response = False
        return

    was_in_combat = state["combat"]["in_combat"]
    campaign = st.session_state.campaign_context

    with st.spinner("The Game Master responds..."):
        new_state, narrative, notices, dice_display = process_player_action(
            state, last_player, campaign_context=campaign)

    st.session_state.game_state = new_state

    # Notices + sounds (pushed first → appear lowest in the reversed chat block)
    for notice in notices:
        if "LEVEL UP" in notice:
            push("level_up", notice)
            st.session_state.pending_sound = "levelup"
        else:
            push("notice", notice)
            if "Found:" in notice:
                st.session_state.pending_sound = "item"
            elif "completed:" in notice.lower() or "quest completed" in notice.lower():
                st.session_state.pending_sound = "quest"

    # Combat started?
    if new_state["combat"]["in_combat"] and not was_in_combat:
        st.session_state.pending_sound = "combat"

    # Death check
    if new_state["player"]["health"] <= 0:
        st.session_state.pending_sound = "death"

    # Scene image
    if st.session_state.image_enabled:
        img_bytes = generate_image(narrative, new_state)
        if img_bytes:
            push("image", base64.b64encode(img_bytes).decode())

    # GM narrative (pushed second → appears above notices)
    push("gm", narrative)

    # Dice pushed last → appears at the very top of this round's block, right below the input
    if dice_display:
        push("dice", dice_display)

    # Voice
    if st.session_state.voice_enabled:
        voice = VOICES.get(st.session_state.voice_name, DEFAULT_VOICE)
        audio = synthesize(narrative, voice)
        st.session_state.pending_audio = audio

    # Multiplayer sync
    if st.session_state.mp_active and st.session_state.mp_session_id:
        mp.push(st.session_state.mp_session_id, new_state)
        st.session_state.mp_last_ts = new_state["multiplayer"]["last_updated"]

    st.session_state.waiting_for_response = False
    st.rerun()


def _mp_sync():
    """Pull latest state from the shared session file and update local chat log."""
    sid = st.session_state.mp_session_id
    if not sid:
        return
    remote = mp.sync(sid)
    if not remote:
        return
    remote_ts = remote.get("multiplayer", {}).get("last_updated", 0)
    if remote_ts <= st.session_state.mp_last_ts:
        return  # nothing new

    st.session_state.game_state = remote
    st.session_state.mp_last_ts = remote_ts

    # Rebuild chat log from history
    st.session_state.chat_log = []
    for entry in remote.get("conversation_history", []):
        t = "gm" if entry["role"] == "assistant" else "player"
        st.session_state.chat_log.append({"type": t, "text": entry["content"]})
    st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────
def main():
    screen = st.session_state.screen

    if screen == "game" and st.session_state.waiting_for_response:
        render_sidebar()
        _process_pending_action()
        return

    if screen == "main_menu":
        screen_main_menu()
    elif screen == "character_creation":
        screen_character_creation()
    elif screen == "load_game":
        screen_load_game()
    elif screen == "multiplayer_lobby":
        screen_multiplayer_lobby()
    elif screen == "game":
        screen_game()
    else:
        screen_main_menu()


main()
