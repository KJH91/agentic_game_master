from __future__ import annotations
import io
import random
from copy import deepcopy

# Grid spacing between location nodes
_STEP = 3
_DIRECTIONS = [(3, 0), (-3, 0), (0, 3), (0, -3), (2, 2), (2, -2), (-2, 2), (-2, -2)]


def init_map() -> dict:
    return {"nodes": {}, "edges": [], "prev_location": None}


def add_location(map_data: dict, new_loc: str, from_loc: str | None) -> dict:
    data = deepcopy(map_data)
    nodes: dict = data.setdefault("nodes", {})
    edges: list = data.setdefault("edges", [])

    if new_loc not in nodes:
        if from_loc and from_loc in nodes:
            fx, fy = nodes[from_loc]["x"], nodes[from_loc]["y"]
        else:
            fx, fy = 0, 0

        placed = False
        for _ in range(20):
            dx, dy = random.choice(_DIRECTIONS)
            nx, ny = fx + dx, fy + dy
            overlap = any(
                abs(d["x"] - nx) <= 1 and abs(d["y"] - ny) <= 1
                for d in nodes.values()
            )
            if not overlap:
                nodes[new_loc] = {"x": nx, "y": ny}
                placed = True
                break

        if not placed:
            # Spiral fallback: place to the right of the rightmost node
            max_x = max((d["x"] for d in nodes.values()), default=0)
            nodes[new_loc] = {"x": max_x + _STEP, "y": 0}

    if from_loc and from_loc != new_loc and from_loc in nodes:
        edge = sorted([from_loc, new_loc])
        if edge not in [sorted(e) for e in edges]:
            edges.append([from_loc, new_loc])

    data["prev_location"] = new_loc
    return data


def render_map_png(game_state: dict) -> bytes | None:
    """Return a dark-themed PNG of the location graph, or None if < 1 node."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        map_data = game_state.get("map", {})
        nodes: dict = map_data.get("nodes", {})
        edges: list = map_data.get("edges", [])
        current = game_state.get("world", {}).get("current_location", "")

        if not nodes:
            return None

        fig, ax = plt.subplots(figsize=(5, 3.5))
        fig.patch.set_facecolor("#0d0d0d")
        ax.set_facecolor("#111111")

        # Edges
        for a, b in edges:
            if a in nodes and b in nodes:
                x0, y0 = nodes[a]["x"], nodes[a]["y"]
                x1, y1 = nodes[b]["x"], nodes[b]["y"]
                ax.plot([x0, x1], [y0, y1], color="#5a3e1b", linewidth=1.5, zorder=1)

        # Nodes
        for name, d in nodes.items():
            x, y = d["x"], d["y"]
            is_cur = name == current
            face = "#c4902a" if is_cur else "#2a1a00"
            edge_c = "#ffd700" if is_cur else "#8a6030"
            circ = plt.Circle((x, y), 0.7, color=face, zorder=2)
            circ.set_edgecolor(edge_c)
            circ.set_linewidth(2 if is_cur else 1)
            ax.add_patch(circ)

            label = name if len(name) <= 14 else name[:13] + "…"
            ax.text(x, y - 1.1, label, ha="center", va="top",
                    fontsize=6, color="#e8d5b0", fontfamily="monospace", zorder=3)

        xs = [d["x"] for d in nodes.values()]
        ys = [d["y"] for d in nodes.values()]
        margin = 2.5
        ax.set_xlim(min(xs) - margin, max(xs) + margin)
        ax.set_ylim(min(ys) - margin - 1.5, max(ys) + margin)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.tight_layout(pad=0.1)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight",
                    facecolor="#0d0d0d", edgecolor="none", dpi=130)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception:
        return None
