# ⚔️ AI Game Master

A locally hosted AI-powered Game Master that runs a fully interactive text-based RPG. Create a character, choose a campaign setting, and let the AI narrate an adaptive story — managing combat, quests, inventory, and persistent state entirely on your own machine.

## Features

- **5 Campaign Settings** — High Fantasy, Dark Fantasy, Sci-Fi, Post-Apocalyptic, Cyberpunk
- **6+ Character Classes** — Warrior, Mage, Rogue, Ranger, Cleric, Paladin (+ Sci-Fi variants)
- **Full Combat System** — Initiative, attack rolls, damage, enemy AI turns — all dice resolved in Python
- **Persistent State** — Full game state saved to JSON; multiple save slots
- **Level Up System** — XP thresholds, stat growth, HP increases, narrative level-up scenes
- **Quest Tracker** — Active and completed quest log with objectives
- **100% Local** — No API keys, no cloud, runs entirely via Ollama on your machine

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Ollama](https://ollama.com/)

## Setup

### 1. Install Ollama

Download and install from [ollama.com](https://ollama.com/), then pull the model:

```bash
ollama pull llama3.2
```

Make sure Ollama is running (it starts automatically after install on most systems).

### 2. Clone / Download the Project

```bash
git clone <your-repo-url>
cd GameMaster
```

Or simply place all project files in a folder.

### 3. Build and Run

```bash
docker-compose up --build
```

First build will take a few minutes to install dependencies.

### 4. Open the App

Navigate to [http://localhost:8502](http://localhost:8502) in your browser.

## Usage

### Starting a New Game

1. Click **New Game** from the main menu
2. Choose your **Campaign Setting** (High Fantasy, Sci-Fi, etc.)
3. Select your **Race / Species** — each has different stat bonuses
4. Pick a **Class** — see starting stats, HP, and playstyle before choosing
5. Enter your **Character Name** and optional backstory
6. Choose **Difficulty** (Story / Standard / Hardcore)
7. Click **Begin Adventure!** — the GM generates your opening scene

### Playing

Type actions in the input box at the bottom and click **Take Action**. Be descriptive:

- `"I approach the hooded figure cautiously and ask what they want."`
- `"I attack the nearest goblin with my longsword."`
- `"I search the room for hidden doors or treasure."`
- `"I try to pickpocket the merchant while distracting him with conversation."`

### Combat

When combat starts, dice are rolled automatically in Python and shown to you before the GM narrates the outcome. The initiative order is displayed, and enemy turns are resolved automatically each round.

### Saving and Loading

- Click **Save** (sidebar or action bar) to save at any time
- Save files are stored in a named Docker volume (`saves_data`) and persist between container restarts
- Click **Load Game** from the main menu to see all saves

## Troubleshooting

### "Connection refused" / Ollama not reachable

- Ensure Ollama is running: open a terminal and run `ollama list`
- On Linux, Docker may need `extra_hosts: host-gateway` — this is already set in `docker-compose.yml`
- On Windows/Mac with Docker Desktop, `host.docker.internal` resolves automatically

### Model not found

```bash
ollama pull llama3.2
```

Run this on your host machine (not inside Docker).

### Save files missing after restart

Save files are stored in a named Docker volume (`saves_data`). Verify with:

```bash
docker volume ls
docker volume inspect gamemaster_saves_data
```

Avoid using `docker-compose down -v` as this removes volumes including your saves.

### Slow responses

`llama3.2` (3B) is the fastest option. For better quality at the cost of speed, edit `game_master.py` and change `MODEL_NAME = "llama3.2"` to `"llama3.2:8b"` or another model you have pulled.

### App crashes / errors

Check container logs:

```bash
docker-compose logs -f gamemaster
```

## Project Structure

```
GameMaster/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── app/
    ├── main.py          # Streamlit UI + screen routing
    ├── game_master.py   # LangChain + Ollama agent logic
    ├── game_state.py    # State creation, updates, save/load
    ├── dice.py          # Dice rolling engine
    └── prompts.py       # System prompts and templates
```

## Configuration

To use a different Ollama model, edit `app/game_master.py`:

```python
MODEL_NAME = "llama3.2"   # change to "mistral", "llama3.2:8b", etc.
```

## Development

The `app/` directory is mounted as a volume in `docker-compose.yml`, so changes to Python files take effect on the next Streamlit rerun without rebuilding the container.
