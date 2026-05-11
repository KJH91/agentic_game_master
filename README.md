# ⚔️ AI Game Master

A self-hosted AI dungeon master running entirely on your computer. Pick a setting, build your character, and let a local AI narrate your adventure — with combat dice, quest tracking, a world map, scene images, GM voice narration, and multiplayer support. No subscription. No internet required to play. Nothing is ever sent to the cloud.

---

## What is this?

You type what your character does. The AI Game Master responds — narrating the story, rolling dice, tracking your quests and inventory, and reacting intelligently to every decision you make. It runs completely on your own machine using free, open-source tools.

**Settings you can play in:**
- 🧙 High Fantasy — swords, magic, dragons
- 🩸 Dark Fantasy — grim, horror, morally grey
- 🚀 Sci-Fi — space exploration, alien worlds
- ☢️ Post-Apocalyptic — wasteland survival
- 🌆 Cyberpunk — megacities, hacking, corporations

---

## Before You Start

You need two free programs installed on your computer before anything else. Don't worry — both have simple installers and you don't need to understand what they do beyond "they make the AI work."

### 1. Install Docker Desktop

Docker is what runs the game. Think of it as a self-contained box that has everything the app needs inside it, so you don't have to install a dozen things manually.

👉 Download here: **https://www.docker.com/products/docker-desktop/**

- Pick the version for your operating system (Windows, Mac, or Linux)
- Run the installer and follow the prompts
- Once installed, open Docker Desktop and wait for it to say **"Engine running"** in the bottom left corner

> ⚠️ On Windows, Docker may ask you to install WSL 2 — follow the prompts, it's automatic.

---

### 2. Install Ollama

Ollama is what runs the AI brain of the Game Master locally on your machine.

👉 Download here: **https://ollama.com/**

- Click Download and run the installer
- Once installed, open a Terminal (Windows: press `Win + R`, type `cmd`, press Enter) and run:

```
ollama pull llama3.2
```

This downloads the AI model (~2 GB). You only need to do this once. When it finishes you'll see a message saying the model is ready.

> 💡 Ollama runs quietly in the background after install. You don't need to open it again.

---

## Setting Up the Game

### Step 1 — Download the project

Click the green **Code** button at the top of this page, then click **Download ZIP**. Extract the ZIP file to anywhere on your computer — your Desktop is fine.

If you have Git installed you can also run:
```
git clone https://github.com/KJH91/agentic_game_master.git
```

---

### Step 2 — Open a Terminal in the project folder

**Windows:**
1. Open the folder you extracted
2. Click the address bar at the top of the window
3. Type `cmd` and press Enter — a terminal window opens in the right place

**Mac:**
1. Open the folder in Finder
2. Right-click anywhere inside it
3. Select **"New Terminal at Folder"**

---

### Step 3 — Start the game

In the terminal, type this and press Enter:

```
docker-compose up --build
```

**The first time you run this it will take a while** — Docker is downloading and building everything it needs (~5–10 minutes depending on your internet speed). You'll see a lot of text scrolling past. This is normal.

You'll know it's ready when you see a line that looks like:

```
gamemaster  | You can now view your Streamlit app in your browser.
```

> 🖼️ **Scene images (optional):** The game also includes an AI image generator that creates pictures of each scene. This downloads an additional ~4 GB model the first time and may take 10–20 minutes. Images will start appearing automatically once it's ready — you can play immediately while it downloads in the background.

---

### Step 4 — Open the game

Open your web browser and go to:

**http://localhost:8502**

You should see the AI Game Master welcome screen. You're ready to play!

---

## How to Play

### Starting a new game

1. Click **New Game**
2. Choose a **campaign setting** — this sets the tone and world of your adventure
3. Pick your **race** — each gives different stat bonuses
4. Pick your **class** — this determines your abilities and playstyle
5. Give your character a **name** (and optionally a backstory)
6. Choose a **difficulty:**
   - *Story Mode* — easier, focused on the narrative
   - *Standard* — balanced challenge
   - *Hardcore* — permadeath, tough enemies
7. Click **Begin Adventure!**

The AI will write your opening scene and your story begins.

---

### Playing the game

At the top of the screen you'll see a text box. Type what you want your character to do and click **Take Action**.

The more descriptive you are, the better the AI responds. For example:

> *"I cautiously approach the wounded soldier and kneel beside him, asking what happened here."*

> *"I draw my sword and charge at the nearest goblin, aiming for its legs."*

> *"I search behind the waterfall for a hidden entrance."*

The Game Master will narrate what happens next. In combat, dice rolls are shown automatically so you can see exactly how outcomes were determined.

---

### Saving your game

Click the **💾 Save** button at any time. Your saves are kept safely on your computer and will still be there after you close everything down.

To continue a saved game, click **Load Game** from the main menu.

> ⚠️ Never run `docker-compose down -v` — the `-v` flag deletes your save files.

---

### Optional features

These can be toggled on and off in the **⚙️ Settings** panel in the sidebar during a game:

| Feature | What it does |
|---|---|
| 🔊 GM Voice | The Game Master reads each response aloud (requires internet) |
| 🎵 Sound Effects | Plays audio cues for combat, level ups, and item finds |
| 🖼️ Scene Images | Generates an AI illustration for each scene (downloads on first run) |

---

### Multiplayer

You can play with friends in the same world. From the main menu:

1. One person clicks **Multiplayer → Host a Session**
2. Complete character creation — a 6-character session code appears in the sidebar
3. Share that code with your friends
4. Friends click **Multiplayer → Join a Session** and enter the code

Everyone sees the same world and can take actions. Hit **🔄 Refresh** to pull in other players' latest moves.

---

### Premade campaigns

If you have an adventure module or campaign document as a PDF, you can upload it during character creation (Step 1). The Game Master will run your story faithfully, using the locations, NPCs, and plot from the document.

---

## Stopping the game

In the terminal where you ran `docker-compose up`, press **Ctrl + C** to stop everything. Your saves are safe.

To start again later, just run `docker-compose up` (no `--build` needed unless you've changed something).

---

## Troubleshooting

### The page at localhost:8502 won't load
Make sure Docker Desktop is open and shows **"Engine running"**. Then check the terminal — if you see any red error text, try stopping with Ctrl+C and running `docker-compose up --build` again.

### "Ollama connection failed" or the AI isn't responding
Ollama needs to be running on your computer. Open a terminal and type `ollama list` — if it responds with a list of models, Ollama is running. If it gives an error, restart your computer and try again.

### The AI model isn't found
Run this in a terminal:
```
ollama pull llama3.2
```

### Responses are very slow
This is normal — the AI is running entirely on your computer. A typical response takes 10–30 seconds depending on your hardware. If it's consistently taking several minutes, your computer may not have enough RAM (8 GB minimum recommended, 16 GB ideal).

### My saves disappeared
This happens if Docker volumes were deleted (usually from running `docker-compose down -v`). Unfortunately saves cannot be recovered after this. Going forward, you can also back up your saves by copying the Docker volume contents or using the built-in Save button regularly.

### Scene images aren't appearing
The image model downloads ~4 GB on first run. Check the terminal for download progress. Once it finishes, enable **Scene Images** in the ⚙️ Settings panel in the sidebar — it will say **"Stable Diffusion ready ✓"** when it's working.

---

## System Requirements

| | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Storage | 15 GB free | 25 GB free |
| OS | Windows 10, macOS 12, Ubuntu 20.04 | Latest version |
| GPU | Not required | NVIDIA GPU speeds up images |

---

## Choosing a different AI model

The game uses `llama3.2` by default which is fast and capable. If you want to experiment with other models, first pull one with Ollama:

```
ollama pull llama3.2:8b
```

Then open `app/game_master.py` in a text editor, find this line near the top, and change the model name:

```python
MODEL_NAME = "llama3.2"
```
