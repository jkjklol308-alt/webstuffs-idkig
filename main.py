import json
import math
import re
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, messagebox, simpledialog


DATA_FILE = Path(__file__).resolve().parent / "data.json"

BG_COLOR = "#121417"
TOPBAR_BG = "#1b1f24"
PANEL_BG = "#181c21"
PANEL_BORDER = "#2d333b"
CARD_BG = "#22272e"
INPUT_BG = "#262c34"
INPUT_FG = "#e6edf3"
MUTED_FG = "#8b949e"
BTN_BG = "#3b82f6"
BTN_ACTIVE_BG = "#2563eb"
BTN_FG = "#ffffff"
SECONDARY_BTN_BG = "#30363d"
SECONDARY_BTN_ACTIVE_BG = "#3d444d"
DANGER_BTN_BG = "#da3633"
DANGER_BTN_ACTIVE_BG = "#b62324"

NODE_FILL = "#22272e"
NODE_OUTLINE = "#444c56"
NODE_SELECTED_OUTLINE = "#3b82f6"
LIQUID_OUTLINE_COLOR = "#38bdf8"  # liquid items get a blue outline (fill colour unchanged)
NODE_TEXT = "#f0f6fc"
NODE_RADIUS = 12
NODE_PAD_X = 18
NODE_PAD_Y = 12
NODE_MIN_W = 110
NODE_MIN_H = 44
NODE_FONT_FAMILY = "Segoe UI"
NODE_FONT_SIZE = 11

# Node size grows with the number of connection lines touching it (in + out).
# A node with 0 connections keeps its base text-fit size (scale 1.0); the scale
# follows a gentle square-root curve and is capped so hubs get bigger but never
# swallow the screen. Sizes are derived, never saved to data.json.
NODE_SCALE_MIN = 1.0
NODE_SCALE_MAX = 2.2
NODE_DEGREE_NORMALIZE = 8.0

# Extra screen pixels drawn around the viewport when culling off-screen items
VIEW_MARGIN_PX = 120

# Line-end interaction: the click/hover circle around a line's end is measured
# in screen pixels, so it stays a usable size at any zoom level
END_HIT_RADIUS_PX = 14
END_DOT_RADIUS_PX = 5
END_DOT_COLOR = "#ffffff"

LINE_WIDTH_NORMAL = 2.2
LINE_WIDTH_SELECTED = 4.0
LINE_WIDTH_DIMMED = 1.6
DIM_BLEND_FACTOR = 0.25  # 25% method colour + 75% canvas background

# Route finding (Shift+click two nodes, highlight every route between them).
# Routes are capped so huge webs cannot freeze the app.
ROUTE_MAX_STEPS = 15  # a route may use at most this many recipes (steps)
ROUTE_MAX_ROUTES = 100  # at most this many routes are collected per direction
ROUTE_HIGHLIGHT_COLOR = "#ffd166"  # bright ring/outline for endpoints and route items
ROUTE_RING_PAD_PX = 6  # ring padding around endpoint nodes, in screen pixels
ROUTE_RING_WIDTH_PX = 3
ROUTE_OUTLINE_WIDTH = 3.2  # outline width of nodes on a route, screen px * zoom
ROUTE_LINE_WIDTH = 5.0  # thicker line width for route lines (method colour kept)
ROUTE_CASING_EXTRA = 3.5  # bright casing drawn under route lines, screen px * zoom

SHIFT_MASK = 0x0001  # Tk modifier bit for the Shift key

MIN_ZOOM = 0.25
MAX_ZOOM = 3.0
ZOOM_STEP = 1.12

PANEL_WIDTH = 360
CLICK_DRAG_THRESHOLD = 5

METHOD_PALETTE = [
    "#f97316",  # Bright Orange
    "#38bdf8",  # Sky Blue
    "#4ade80",  # Bright Green
    "#facc15",  # Sunny Yellow
    "#c084fc",  # Bright Purple
    "#f43f5e",  # Rose Pink
    "#2dd4bf",  # Teal / Mint
    "#fb923c",  # Amber Peach
    "#60a5fa",  # Cornflower Blue
    "#a3e635",  # Lime
    "#e879f9",  # Magenta
    "#f87171",  # Coral Red
    "#22d3ee",  # Cyan
    "#fde047",  # Lemon
]


def _normalize_hex_color(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            return None
    return None


def hex_to_rgb(hex_color):
    color = hex_color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def rgb_to_hex(r, g, b):
    r = max(0, min(255, int(round(r))))
    g = max(0, min(255, int(round(g))))
    b = max(0, min(255, int(round(b))))
    return f"#{r:02x}{g:02x}{b:02x}"


def blend_colors(fg_hex, bg_hex, factor):
    fr, fg, fb = hex_to_rgb(fg_hex)
    br, bg, bb = hex_to_rgb(bg_hex)
    r = br + (fr - br) * factor
    g = bg + (fg - bg) * factor
    b = bb + (fb - bb) * factor
    return rgb_to_hex(r, g, b)


# --- Per-node custom colours (persisted in data.json) ---


def node_fill_color(node):
    """The node's custom colour if one is set and valid, otherwise the default."""
    return _normalize_hex_color(node.get("color")) or NODE_FILL


def best_text_color_for(bg_hex):
    """Black or near-white text, whichever is easier to read on this background."""
    r, g, b = hex_to_rgb(bg_hex)
    yiq = (r * 299 + g * 587 + b * 114) / 1000.0
    return "#000000" if yiq >= 128 else NODE_TEXT


def dimmed_toward_background(hex_color):
    """Blend a colour toward the canvas background (same as dimmed lines)."""
    return blend_colors(hex_color, BG_COLOR, DIM_BLEND_FACTOR)


# --- Route finding (Shift+click two nodes, then highlight every route between them) ---


def _name_key(name):
    return str(name).strip().lower()


def _route_edge_key(path, in_name, out_name):
    """Identity of one drawn line: the path object plus its input/output pair."""
    return (id(path), _name_key(in_name), _name_key(out_name))


def edge_walk_directions(path, in_name, out_name):
    """Which ways one line can be walked, decided by its arrowheads.

    A head at the finish end (the output side) lets a route walk input -> output;
    a head at the start end (the input side) lets it walk output -> input; two
    heads allow both; no heads mean the line cannot be walked at all.
    """
    cfg = get_edge_arrows(path, in_name, out_name)
    return {"fwd": bool(cfg["finish"]), "rev": bool(cfg["start"])}


def build_route_adjacency(paths):
    """Adjacency of walkable recipe steps: node key -> list of step dicts.

    Each step walks one recipe (path) from one of its inputs to one of its
    outputs, in a direction the line's arrowheads allow ("walk": "fwd" =
    input -> output, "rev" = output -> input). Outputs with a 0% chance are
    never walked.
    """
    adj = {}
    for path in paths:
        method = path.get("method", "")
        for in_name in path.get("inputs", []):
            for out_name in path.get("outputs", []):
                if output_chance(path, out_name) <= 0:
                    continue  # a 0% output can never be produced, so never walked
                base = {
                    "method": method,
                    "path": path,
                    "in_name": str(in_name),
                    "out_name": str(out_name),
                }
                walk = edge_walk_directions(path, in_name, out_name)
                if walk["fwd"]:
                    adj.setdefault(_name_key(in_name), []).append({
                        **base,
                        "src": str(in_name),
                        "dst": str(out_name),
                        "src_key": _name_key(in_name),
                        "dst_key": _name_key(out_name),
                        "walk": "fwd",
                    })
                if walk["rev"]:
                    adj.setdefault(_name_key(out_name), []).append({
                        **base,
                        "src": str(out_name),
                        "dst": str(in_name),
                        "src_key": _name_key(out_name),
                        "dst_key": _name_key(in_name),
                        "walk": "rev",
                    })
    return adj


def search_routes(paths, start_name, end_name,
                  max_steps=ROUTE_MAX_STEPS, max_routes=ROUTE_MAX_ROUTES):
    """All simple routes (no node used twice) from start to end, walking each
    line only in a direction its arrowheads allow.

    Returns (routes, limit_hit). Each route is a list of recipe-step dicts in
    traversal order. A route is at most max_steps recipes long, and at most
    max_routes routes are collected (limit_hit=True when that cap was reached).
    """
    start_key = _name_key(start_name)
    end_key = _name_key(end_name)
    routes = []
    if start_key == end_key:
        return routes, False
    adj = build_route_adjacency(paths)
    limit_hit = False
    visited = {start_key}
    stack = []

    def dfs(cur_key):
        nonlocal limit_hit
        if cur_key == end_key:
            routes.append(list(stack))
            if len(routes) >= max_routes:
                limit_hit = True
            return
        if limit_hit or len(stack) >= max_steps:
            return
        for edge in adj.get(cur_key, []):
            if limit_hit:
                return
            nxt = edge["dst_key"]
            if nxt in visited:
                continue
            visited.add(nxt)
            stack.append(edge)
            dfs(nxt)
            stack.pop()
            visited.discard(nxt)

    dfs(start_key)
    return routes, limit_hit


def find_routes(paths, start_name, end_name,
                max_steps=ROUTE_MAX_STEPS, max_routes=ROUTE_MAX_ROUTES):
    """Routes between two items in BOTH directions (arrowheads only — there is
    no direction-ignoring fallback anymore).

    Returns (directions, limit_hit) where directions is a list of
    (from_name, to_name, routes) — first start -> end, then end -> start.
    limit_hit is True when either direction reached the route cap.
    """
    directions = []
    limit_hit = False
    for a, b in ((start_name, end_name), (end_name, start_name)):
        routes, hit = search_routes(
            paths, a, b, max_steps=max_steps, max_routes=max_routes
        )
        directions.append((str(a), str(b), routes))
        limit_hit = limit_hit or hit
    return directions, limit_hit


def step_also_inputs(step):
    """Inputs of a route step's recipe besides the one being walked
    (the recipe's "also needs" items)."""
    walked = _name_key(step["in_name"])
    return [n for n in step["path"].get("inputs", []) if _name_key(n) != walked]


def format_route_step(step, node_by_key=None):
    """One route step, e.g. '-(Washing, 25%)-> 1 Flint', or with extra required
    inputs: '-(Mixing, also needs 1 Flint, 50 mB Lava)-> 1 Veridium'."""
    path = step["path"]
    bits = [str(step["method"])]
    chance = output_chance(path, step["out_name"])
    if chance != 100.0:
        bits.append(f"{format_chance(chance)}%")
    also = step_also_inputs(step)
    if also:
        bits.append(
            "also needs "
            + ", ".join(
                format_amount(input_amount(path, n), n, node_by_key) for n in also
            )
        )
    if step.get("walk") == "rev":
        # Walking output -> input: the destination is the recipe's input
        dst_amount = input_amount(path, step["in_name"])
    else:
        dst_amount = output_amount(path, step["out_name"])
    return f"-({', '.join(bits)})-> {format_amount(dst_amount, step['dst'], node_by_key)}"


def format_route(route, node_by_key=None):
    """One route as a single line, e.g.
    'Cobblestone -(Crushing)-> 1 Gravel -(Washing, 25%)-> 1 Flint'."""
    if not route:
        return ""
    parts = [str(route[0]["src"])]
    for step in route:
        parts.append(format_route_step(step, node_by_key))
    return " ".join(parts)


def _parse_item_list(raw_items):
    if not isinstance(raw_items, list):
        return []
    cleaned = []
    seen = set()
    for item in raw_items:
        text = str(item).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            cleaned.append(text)
    return cleaned


def parse_comma_separated(text):
    cleaned = []
    seen = set()
    for part in text.split(","):
        item = part.strip()
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            cleaned.append(item)
    return cleaned


# --- Per-output chances (percentages, persisted in data.json inside each path) ---

OUTPUT_CHANCE_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?")


def parse_output_entry(text):
    """Parse one Outputs-box entry: 'Name' or 'Name 25%' (percent sign optional).

    Returns (name, chance) where chance is a float in 0..100 or None (=> 100%).
    Raises ValueError with a user-facing message on an invalid number.
    """
    part = text.strip()
    if not part:
        return None, None
    tokens = part.split()
    chance = None
    if len(tokens) > 1 and OUTPUT_CHANCE_TOKEN_RE.fullmatch(tokens[-1]):
        try:
            chance = float(tokens[-1].rstrip("%"))
        except ValueError:
            raise ValueError(f'Invalid percentage "{tokens[-1]}" in "{part}".')
        part = " ".join(tokens[:-1])
    elif len(tokens) == 1 and OUTPUT_CHANCE_TOKEN_RE.fullmatch(tokens[0]):
        raise ValueError(f'Missing item name before "{tokens[0]}".')
    elif any("%" in t or re.search(r"\d", t) for t in tokens[1:]):
        # trailing text that looks like a mistyped percentage
        raise ValueError(f'Invalid percentage in "{part}". Use e.g. "Flint 25%".')
    if not part:
        raise ValueError("Missing item name.")
    if chance is not None and not 0.0 <= chance <= 100.0:
        raise ValueError(f'Percentage for "{part}" must be between 0 and 100.')
    return part, chance


def parse_outputs_with_chances(text):
    """Parse the Outputs box into [(name, chance_or_None)], deduped case-insensitively."""
    entries = []
    seen = set()
    for part in text.split(","):
        name, chance = parse_output_entry(part)
        if name is None:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append((name, chance))
    return entries


# --- Per-item amounts (whole number >= 1, default 1; typed before the name) ---

AMOUNT_MAX = 10 ** 9


class AmountError(ValueError):
    """Raised when an amount prefix is not a whole number >= 1."""


AMOUNT_TOKEN_RE = re.compile(r"^(\d+)[xX]?$")
AMOUNT_LIKE_RE = re.compile(r"^[-+]?\d")


def parse_amount_prefix(tokens):
    """Split an optional leading amount ('3' or '3x') off the token list.

    Returns (amount_or_None, remaining_tokens). Raises AmountError when the
    first token looks like a number but is not a valid whole number >= 1.
    """
    if not tokens:
        return None, tokens
    first = tokens[0]
    m = AMOUNT_TOKEN_RE.fullmatch(first)
    if m:
        amount = int(m.group(1))
        if amount < 1:
            raise AmountError(f'amount "{first}" must be a whole number of at least 1')
        if amount > AMOUNT_MAX:
            raise AmountError(f'amount "{first}" is too large')
        return amount, tokens[1:]
    if AMOUNT_LIKE_RE.match(first):
        raise AmountError(
            f'invalid amount "{first}" — use a whole number of at least 1 before the '
            f'name, e.g. "3 Clay" or "3x Clay"'
        )
    return None, tokens


def parse_path_item(text, allow_chance):
    """Parse one box entry: '[amount] Name [chance%]'.

    Returns (name, amount, chance) with amount >= 1 (default 1) and chance a
    float 0..100 or None. Raises AmountError / ValueError on bad input.
    """
    part = text.strip()
    if not part:
        return None
    tokens = part.split()
    amount, tokens = parse_amount_prefix(tokens)
    rest = " ".join(tokens)
    if allow_chance:
        name, chance = parse_output_entry(rest)
        if name is None:
            raise AmountError("missing item name after the amount")
    else:
        name, chance = rest, None
        if not name:
            raise AmountError("missing item name after the amount")
    return name, (1 if amount is None else amount), chance


def parse_inputs_with_amounts(text):
    """Parse the Inputs box into [(name, amount)], deduped case-insensitively."""
    entries = []
    seen = set()
    for part in text.split(","):
        parsed = parse_path_item(part, allow_chance=False)
        if parsed is None:
            continue
        name, amount, _chance = parsed
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append((name, amount))
    return entries


def parse_outputs_with_amounts_chances(text):
    """Parse the Outputs box into [(name, amount, chance_or_None)], deduped."""
    entries = []
    seen = set()
    for part in text.split(","):
        parsed = parse_path_item(part, allow_chance=True)
        if parsed is None:
            continue
        name, amount, chance = parsed
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append((name, amount, chance))
    return entries


def normalize_chances(raw):
    """Keep only valid {output_key: chance 0..100} entries (keys lowercased)."""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for k, v in raw.items():
        key = str(k).strip().lower()
        if not key or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        v = float(v)
        if 0.0 <= v <= 100.0:
            cleaned[key] = v
    return cleaned


def output_chance(path, out_name):
    """The chance for one output item; outputs without a saved chance are 100%."""
    chances = path.get("chances")
    if isinstance(chances, dict):
        v = chances.get(str(out_name).strip().lower())
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 100.0:
            return float(v)
    return 100.0


def format_chance(value):
    return f"{float(value):g}"


def format_input_entry(path, in_name):
    """One input as typed in the Inputs box, e.g. '3 Clay' (amount always shown)."""
    return f"{input_amount(path, in_name)} {in_name}"


def format_output_entry(path, out_name):
    """One output as typed in the Outputs box, e.g. '1 Flint 25%' (chance shown only if set)."""
    base = f"{output_amount(path, out_name)} {out_name}"
    chances = path.get("chances")
    key = str(out_name).strip().lower()
    if isinstance(chances, dict) and key in chances:
        base += f" {format_chance(chances[key])}%"
    return base


# --- Amount accessors (stored per path as {"inputs": {key: n}, "outputs": {key: n}}) ---


def normalize_amounts(raw):
    """Keep only valid amounts: {"inputs"/"outputs": {lower name: whole number 1..AMOUNT_MAX}}."""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for side in ("inputs", "outputs"):
        sub = raw.get(side)
        if not isinstance(sub, dict):
            continue
        clean_sub = {}
        for k, v in sub.items():
            key = str(k).strip().lower()
            if not key or isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            if isinstance(v, float) and not v.is_integer():
                continue
            iv = int(v)
            if 1 <= iv <= AMOUNT_MAX:
                clean_sub[key] = iv
        if clean_sub:
            cleaned[side] = clean_sub
    return cleaned


def _amount_lookup(path, side, name):
    amounts = path.get("amounts")
    if isinstance(amounts, dict):
        sub = amounts.get(side)
        if isinstance(sub, dict):
            v = sub.get(str(name).strip().lower())
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                iv = int(v)
                if 1 <= iv <= AMOUNT_MAX:
                    return iv
    return 1


def input_amount(path, in_name):
    """Amount of one input item in a path; defaults to 1."""
    return _amount_lookup(path, "inputs", in_name)


def output_amount(path, out_name):
    """Amount of one output item in a path; defaults to 1."""
    return _amount_lookup(path, "outputs", out_name)


def prune_path_amounts(path):
    """Drop amounts for items no longer in the path (node deletion / path edit)."""
    amounts = path.get("amounts")
    if not isinstance(amounts, dict):
        return
    valid = {
        "inputs": {str(i).strip().lower() for i in path.get("inputs", [])},
        "outputs": {str(o).strip().lower() for o in path.get("outputs", [])},
    }
    cleaned = {}
    for side, keys in valid.items():
        sub = amounts.get(side)
        if isinstance(sub, dict):
            c = {k: v for k, v in sub.items() if k in keys}
            if c:
                cleaned[side] = c
    if cleaned:
        path["amounts"] = cleaned
    else:
        path.pop("amounts", None)


# --- Item types: every item is an "item" or a "liquid" (default item) ---


def normalize_node_type(value):
    return "liquid" if str(value).strip().lower() == "liquid" else "item"


def node_type(node):
    """The item's type: 'item' (default) or 'liquid'."""
    return normalize_node_type(node.get("type"))


def is_liquid(node):
    return node_type(node) == "liquid"


def format_amount(amount, name, node_by_key=None):
    """'3 Clay' for normal items, '50 mB Lava' for liquids (when types are known)."""
    if node_by_key is not None:
        node = node_by_key.get(str(name).strip().lower())
        if node is not None and is_liquid(node):
            return f"{int(amount)} mB {name}"
    return f"{int(amount)} {name}"


def format_path(path, node_by_key=None):
    """Side-panel path text with amounts, e.g.
    'Mixing: 3 Clay + 1 Flint + 50 mB Lava -> 1 Veridium (100%), 1 Flint (25%)'."""
    method = path["method"]
    inputs_str = " + ".join(
        format_amount(input_amount(path, n), n, node_by_key) for n in path["inputs"]
    )
    outputs_str = ", ".join(
        f"{format_amount(output_amount(path, n), n, node_by_key)} "
        f"({format_chance(output_chance(path, n))}%)"
        for n in path["outputs"]
    )
    return f"{method}: {inputs_str} \u2192 {outputs_str}"


def path_involves_item(path, item_name):
    target = item_name.strip().lower()
    if not target:
        return False
    for name in path.get("inputs", []):
        if name.strip().lower() == target:
            return True
    for name in path.get("outputs", []):
        if name.strip().lower() == target:
            return True
    return False


def pick_next_palette_color(existing_colors):
    used = {c.lower() for c in existing_colors.values()}
    for color in METHOD_PALETTE:
        if color.lower() not in used:
            return color.lower()
    return METHOD_PALETTE[len(existing_colors) % len(METHOD_PALETTE)].lower()


# --- Per-line-end arrowhead settings (persisted inside each path in data.json) ---

ARROW_START_DEFAULT = False  # start end (at the input node) has no arrowhead by default
ARROW_FINISH_DEFAULT = True  # finish end (at the output node) has an arrowhead by default


def arrow_pair_key(in_name, out_name):
    """Stable key identifying one line: the path's input/output pair."""
    return json.dumps([str(in_name).strip(), str(out_name).strip()], ensure_ascii=False)


def normalize_arrow_config(value):
    if not isinstance(value, dict):
        return None
    start = value.get("start", ARROW_START_DEFAULT)
    finish = value.get("finish", ARROW_FINISH_DEFAULT)
    if not isinstance(start, bool) or not isinstance(finish, bool):
        return None
    return {"start": start, "finish": finish}


def normalize_arrows(raw):
    """Keep only valid {pair_key: {"start": bool, "finish": bool}} entries."""
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key:
            continue
        cfg = normalize_arrow_config(value)
        if cfg is not None:
            cleaned[key] = cfg
    return cleaned


def get_edge_arrows(path, in_name, out_name):
    """Arrowhead config for one line; defaults to a finish-end-only arrow."""
    arrows = path.get("arrows")
    if isinstance(arrows, dict):
        cfg = normalize_arrow_config(arrows.get(arrow_pair_key(in_name, out_name)))
        if cfg is not None:
            return cfg
    return {"start": ARROW_START_DEFAULT, "finish": ARROW_FINISH_DEFAULT}


def set_edge_arrows(path, in_name, out_name, config):
    arrows = path.get("arrows")
    if not isinstance(arrows, dict):
        arrows = {}
        path["arrows"] = arrows
    arrows[arrow_pair_key(in_name, out_name)] = {
        "start": bool(config.get("start", ARROW_START_DEFAULT)),
        "finish": bool(config.get("finish", ARROW_FINISH_DEFAULT)),
    }


def prune_path_arrows(path):
    """Drop arrowhead settings for input/output pairs no longer in the path.

    Used when an item is removed from a path (node deletion or path editing):
    line-end settings belong to the path, so pairs that vanished go with them.
    """
    arrows = path.get("arrows")
    if not isinstance(arrows, dict):
        return
    valid = {
        arrow_pair_key(i, o)
        for i in path.get("inputs", [])
        for o in path.get("outputs", [])
    }
    cleaned = {k: v for k, v in arrows.items() if k in valid}
    if cleaned:
        path["arrows"] = cleaned
    else:
        path.pop("arrows", None)


def prune_path_chances(path):
    """Drop chances for outputs no longer in the path (node deletion / path edit)."""
    chances = path.get("chances")
    if not isinstance(chances, dict):
        return
    valid = {str(o).strip().lower() for o in path.get("outputs", [])}
    cleaned = {k: v for k, v in chances.items() if k in valid}
    if cleaned:
        path["chances"] = cleaned
    else:
        path.pop("chances", None)


def rename_item_everywhere(nodes, paths, old_name, new_name):
    """Rename an item in place: its node plus every reference in the paths —
    the inputs/outputs lists, the per-pair arrowhead keys and the per-output
    chance keys all follow the new name (matching is case-insensitive)."""
    old_key = _name_key(old_name)
    new_chance_key = new_name.strip().lower()
    for node in nodes:
        if _name_key(node.get("name", "")) == old_key:
            node["name"] = new_name
    for path in paths:
        path["inputs"] = [
            new_name if _name_key(n) == old_key else n for n in path.get("inputs", [])
        ]
        path["outputs"] = [
            new_name if _name_key(n) == old_key else n for n in path.get("outputs", [])
        ]
        arrows = path.get("arrows")
        if isinstance(arrows, dict) and arrows:
            remapped = {}
            for key, cfg in arrows.items():
                try:
                    pair = json.loads(key)
                    in_name, out_name = str(pair[0]), str(pair[1])
                except (ValueError, TypeError, IndexError):
                    remapped[key] = cfg
                    continue
                if _name_key(in_name) == old_key:
                    in_name = new_name
                if _name_key(out_name) == old_key:
                    out_name = new_name
                remapped[arrow_pair_key(in_name, out_name)] = cfg
            path["arrows"] = remapped
        chances = path.get("chances")
        if isinstance(chances, dict) and chances:
            path["chances"] = {
                (new_chance_key if _name_key(k) == old_key else k): v
                for k, v in chances.items()
            }
        amounts = path.get("amounts")
        if isinstance(amounts, dict) and amounts:
            remapped_amounts = {}
            for side in ("inputs", "outputs"):
                sub = amounts.get(side)
                if isinstance(sub, dict) and sub:
                    remapped_amounts[side] = {
                        (new_chance_key if _name_key(k) == old_key else k): v
                        for k, v in sub.items()
                    }
            path["amounts"] = remapped_amounts


def load_data():
    if not DATA_FILE.exists():
        return [], [], {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        # Support legacy list format and dict format with nodes, paths, method_colors
        if isinstance(raw, list):
            raw_nodes = raw
            raw_paths = []
            raw_colors = {}
        elif isinstance(raw, dict):
            raw_nodes = raw.get("nodes", [])
            raw_paths = raw.get("paths", [])
            raw_colors = raw.get("method_colors", {})
        else:
            return [], [], {}

        nodes = []
        seen_nodes = set()
        if isinstance(raw_nodes, list):
            for entry in raw_nodes:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                if not name or name.lower() in seen_nodes:
                    continue
                try:
                    x = float(entry.get("x", 100))
                    y = float(entry.get("y", 100))
                except (TypeError, ValueError):
                    x, y = 100.0, 100.0
                seen_nodes.add(name.lower())
                node_entry = {"name": name, "x": x, "y": y}
                # Custom node colour, if one was saved (otherwise default applies)
                color = _normalize_hex_color(entry.get("color"))
                if color:
                    node_entry["color"] = color
                # Item type: only "liquid" is stored, everything else is the default "item"
                if normalize_node_type(entry.get("type")) == "liquid":
                    node_entry["type"] = "liquid"
                nodes.append(node_entry)

        method_colors = {}
        if isinstance(raw_colors, dict):
            for k, v in raw_colors.items():
                key = str(k).strip().lower()
                color = _normalize_hex_color(v)
                if key and color:
                    method_colors[key] = color

        paths = []
        if isinstance(raw_paths, list):
            for entry in raw_paths:
                if not isinstance(entry, dict):
                    continue
                method = str(entry.get("method", "")).strip()
                inputs = _parse_item_list(entry.get("inputs", []))
                outputs = _parse_item_list(entry.get("outputs", []))
                if not method or not inputs or not outputs:
                    continue
                mkey = method.lower()
                if mkey not in method_colors:
                    method_colors[mkey] = pick_next_palette_color(method_colors)
                path_entry = {
                    "method": method,
                    "inputs": inputs,
                    "outputs": outputs,
                }
                # Per-line arrowhead settings live inside the path, so deleting
                # the path deletes them too
                arrows = normalize_arrows(entry.get("arrows", {}))
                if arrows:
                    path_entry["arrows"] = arrows
                # Per-output chances also live inside the path; paths saved
                # before this feature simply have no key and read as 100%
                chances = normalize_chances(entry.get("chances"))
                if chances:
                    path_entry["chances"] = chances
                # Per-item amounts; paths saved before this feature have no key
                # and read as amount 1 for every input and output
                amounts = normalize_amounts(entry.get("amounts"))
                if amounts:
                    path_entry["amounts"] = amounts
                paths.append(path_entry)

        return nodes, paths, method_colors
    except (OSError, json.JSONDecodeError):
        return [], [], {}


def _node_save_entry(node):
    entry = {"name": node["name"], "x": round(node["x"], 2), "y": round(node["y"], 2)}
    # Nodes without a custom colour are simply saved without a "color" key
    color = _normalize_hex_color(node.get("color"))
    if color:
        entry["color"] = color
    # Only non-default types are stored ("liquid"); "item" is the default
    if normalize_node_type(node.get("type")) == "liquid":
        entry["type"] = "liquid"
    return entry


def save_data(nodes, paths, method_colors):
    payload = {
        "nodes": [_node_save_entry(node) for node in nodes],
        "paths": [
            {
                "method": path["method"],
                "inputs": list(path["inputs"]),
                "outputs": list(path["outputs"]),
                **({"arrows": normalize_arrows(path["arrows"])} if path.get("arrows") else {}),
                **({"chances": normalize_chances(path["chances"])} if path.get("chances") else {}),
                **({"amounts": normalize_amounts(path["amounts"])} if path.get("amounts") else {}),
            }
            for path in paths
        ],
        "method_colors": dict(method_colors),
    }
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def rounded_rect_points(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1,
        x1 + r, y1,
        x2 - r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1 + r,
        x1, y1,
    ]


def rect_border_point(cx, cy, half_w, half_h, dir_x, dir_y, pad=3.0):
    if abs(dir_x) < 1e-6 and abs(dir_y) < 1e-6:
        return cx, cy
    tx = (half_w + pad) / abs(dir_x) if abs(dir_x) > 1e-6 else float("inf")
    ty = (half_h + pad) / abs(dir_y) if abs(dir_y) > 1e-6 else float("inf")
    t = min(tx, ty)
    return cx + dir_x * t, cy + dir_y * t


# --- Connection-driven node sizing (calculated, never persisted) ---


def connection_degree_counts(paths):
    """Count, per item name, how many lines go out of it plus into it.

    Every (input, output) pair of a path is one directed line, so an input
    item gains len(outputs) outgoing lines and an output item gains
    len(inputs) incoming lines. An item that is both input and output of the
    same path is counted for both directions (self-loop = 2).
    """
    counts = {}
    for path in paths:
        inputs = path.get("inputs", [])
        outputs = path.get("outputs", [])
        for name in inputs:
            key = str(name).strip().lower()
            if key:
                counts[key] = counts.get(key, 0) + len(outputs)
        for name in outputs:
            key = str(name).strip().lower()
            if key:
                counts[key] = counts.get(key, 0) + len(inputs)
    return counts


def node_scale_for_degree(degree):
    """Gentle square-root growth from NODE_SCALE_MIN up to the NODE_SCALE_MAX cap."""
    if degree <= 0:
        return NODE_SCALE_MIN
    return min(NODE_SCALE_MAX, math.sqrt(1.0 + degree / NODE_DEGREE_NORMALIZE))


def recalculate_node_sizes(canvas, nodes, paths):
    """Recompute every node's connection count, scale and world size in place.

    Sizes are derived from the current paths on every call, so they update
    immediately whenever a path is added or deleted. Only name/x/y are ever
    written to data.json.
    """
    counts = connection_degree_counts(paths)
    for node in nodes:
        key = node["name"].strip().lower()
        degree = counts.get(key, 0)
        node["connections"] = degree
        scale = node_scale_for_degree(degree)
        node["scale"] = scale
        base_w, base_h = measure_node_base_size(canvas, node)
        node["base_width"] = base_w
        node["base_height"] = base_h
        node["width"] = base_w * scale
        node["height"] = base_h * scale


# --- Infinite-canvas viewport culling ---


def visible_world_rect(view_w, view_h, zoom, pan_x, pan_y, margin=VIEW_MARGIN_PX):
    """World-coordinate rectangle currently on screen, plus a small margin."""
    if zoom <= 1e-6:
        zoom = 1.0
    x1 = (-margin - pan_x) / zoom
    y1 = (-margin - pan_y) / zoom
    x2 = (view_w + margin - pan_x) / zoom
    y2 = (view_h + margin - pan_y) / zoom
    return (x1, y1, x2, y2)


def node_intersects_rect(node, rect):
    """True if the node's (scaled) world-space box touches the given world rect."""
    x1, y1, x2, y2 = rect
    half_w = node.get("width", NODE_MIN_W) / 2.0
    half_h = node.get("height", NODE_MIN_H) / 2.0
    x = node["x"]
    y = node["y"]
    return not (x + half_w < x1 or x - half_w > x2 or y + half_h < y1 or y - half_h > y2)


def segment_intersects_rect(x1, y1, x2, y2, rx1, ry1, rx2, ry2):
    """True if the segment (x1,y1)-(x2,y2) touches or crosses the rect."""
    if max(x1, x2) < rx1 or min(x1, x2) > rx2 or max(y1, y2) < ry1 or min(y1, y2) > ry2:
        return False

    def inside(x, y):
        return rx1 <= x <= rx2 and ry1 <= y <= ry2

    if inside(x1, y1) or inside(x2, y2):
        return True

    def cross(ox, oy, px, py, qx, qy):
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    def segments_hit(ax, ay, bx, by, cx, cy, dx, dy):
        d1 = cross(cx, cy, dx, dy, ax, ay)
        d2 = cross(cx, cy, dx, dy, bx, by)
        d3 = cross(ax, ay, bx, by, cx, cy)
        d4 = cross(ax, ay, bx, by, dx, dy)
        return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))

    edges = (
        (rx1, ry1, rx2, ry1),
        (rx2, ry1, rx2, ry2),
        (rx2, ry2, rx1, ry2),
        (rx1, ry2, rx1, ry1),
    )
    for ex1, ey1, ex2, ey2 in edges:
        if segments_hit(x1, y1, x2, y2, ex1, ey1, ex2, ey2):
            return True
    return False


def measure_node_base_size(canvas, node):
    if "base_width" in node and "base_height" in node:
        return node["base_width"], node["base_height"]

    probe_id = canvas.create_text(
        0,
        0,
        text=node["name"],
        font=(NODE_FONT_FAMILY, NODE_FONT_SIZE, "bold"),
    )
    bbox = canvas.bbox(probe_id)
    canvas.delete(probe_id)

    if bbox:
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w = len(node["name"]) * 8
        text_h = 18

    base_w = max(NODE_MIN_W, text_w + NODE_PAD_X * 2)
    base_h = max(NODE_MIN_H, text_h + NODE_PAD_Y * 2)
    node["base_width"] = base_w
    node["base_height"] = base_h
    return base_w, base_h


def draw_node(canvas, node, tag, selected=False, zoom=1.0, pan_x=0.0, pan_y=0.0,
              dimmed=False, ring=False, highlighted=False):
    base_w, base_h = measure_node_base_size(canvas, node)
    scale = node.get("scale") or NODE_SCALE_MIN
    # World-space size already includes the connection-driven scale
    world_w = node.get("width") or base_w * scale
    world_h = node.get("height") or base_h * scale

    sx = node["x"] * zoom + pan_x
    sy = node["y"] * zoom + pan_y
    width = world_w * zoom
    height = world_h * zoom
    radius = NODE_RADIUS * zoom * scale

    # Custom node colour (default when unset); text picks black/white for contrast
    fill_color = node_fill_color(node)
    text_color = best_text_color_for(fill_color)
    if dimmed:
        # Dimmed nodes blend toward the background, like the dimmed lines
        fill_color = dimmed_toward_background(fill_color)
        text_color = dimmed_toward_background(text_color)

    # Text grows together with the node (base text size * connection scale)
    font_size = max(4, int(round(NODE_FONT_SIZE * scale * zoom)))
    if highlighted:
        # Node on a route: bright outline, full (custom) fill colour
        outline_w = max(1.5, ROUTE_OUTLINE_WIDTH * zoom)
        outline_color = ROUTE_HIGHLIGHT_COLOR
    elif selected:
        outline_w = max(1.0, 2.5 * zoom)
        outline_color = NODE_SELECTED_OUTLINE
    elif is_liquid(node):
        # Liquids get a blue outline; the fill colour stays exactly as it is
        outline_w = max(1.0, 2.0 * zoom)
        outline_color = LIQUID_OUTLINE_COLOR
    else:
        outline_w = max(1.0, 2.0 * zoom)
        outline_color = NODE_OUTLINE

    x1, y1 = sx - width / 2.0, sy - height / 2.0
    x2, y2 = sx + width / 2.0, sy + height / 2.0

    points = rounded_rect_points(x1, y1, x2, y2, radius)
    rect_id = canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=24,
        fill=fill_color,
        outline=outline_color,
        width=outline_w,
        tags=(tag, "node"),
    )
    text_id = canvas.create_text(
        sx,
        sy,
        text=node["name"],
        fill=text_color,
        font=(NODE_FONT_FAMILY, font_size, "bold"),
        tags=(tag, "node"),
    )
    canvas.tag_raise(text_id, rect_id)

    # Bright outline ring around route endpoint nodes; padding is in screen
    # pixels, so the ring keeps the same visible size at any zoom level
    if ring:
        pad = ROUTE_RING_PAD_PX * zoom
        ring_points = rounded_rect_points(x1 - pad, y1 - pad, x2 + pad, y2 + pad, radius + pad)
        ring_id = canvas.create_polygon(
            ring_points,
            smooth=True,
            splinesteps=24,
            fill="",
            outline=ROUTE_HIGHLIGHT_COLOR,
            width=max(2.0, ROUTE_RING_WIDTH_PX * zoom),
            tags=(tag, "node"),
        )
        canvas.tag_raise(ring_id, rect_id)
        node["ring_id"] = ring_id
    else:
        node["ring_id"] = None

    node["tag"] = tag
    node["rect_id"] = rect_id
    node["text_id"] = text_id
    node["width"] = world_w
    node["height"] = world_h


def draw_connections(
    canvas,
    nodes,
    paths,
    method_colors,
    selected_node=None,
    zoom=1.0,
    pan_x=0.0,
    pan_y=0.0,
    view_rect=None,
    edge_sink=None,
    route_edge_keys=None,
    route_also_keys=None,
    routes_active=False,
):
    canvas.delete("connection")
    if edge_sink is not None:
        edge_sink.clear()
    if not paths or not nodes:
        return

    node_by_key = {n["name"].strip().lower(): n for n in nodes}
    selected_key = selected_node["name"].strip().lower() if selected_node else None

    # Group edges by unordered node pair so multiple arrows between the same 2 nodes fan out cleanly
    raw_edges = []
    pair_buckets = {}

    for path in paths:
        method_key = path["method"].strip().lower()
        base_color = method_colors.get(method_key, METHOD_PALETTE[0])

        for in_name in path["inputs"]:
            src = node_by_key.get(in_name.strip().lower())
            if src is None:
                continue
            for out_name in path["outputs"]:
                dst = node_by_key.get(out_name.strip().lower())
                if dst is None:
                    continue

                src_key = src["name"].strip().lower()
                dst_key = dst["name"].strip().lower()
                connected_to_selected = (
                    selected_key is not None
                    and (src_key == selected_key or dst_key == selected_key)
                )

                on_route = bool(
                    routes_active
                    and route_edge_keys is not None
                    and _route_edge_key(path, in_name, out_name) in route_edge_keys
                )
                # Extra input line required by a route recipe (its "also needs"):
                # drawn dashed bright, but not walked as part of the route
                also_needed = bool(
                    routes_active
                    and route_also_keys is not None
                    and _route_edge_key(path, in_name, out_name) in route_also_keys
                )
                edge = {
                    "src": src,
                    "dst": dst,
                    "src_key": src_key,
                    "dst_key": dst_key,
                    "color": base_color,
                    "connected": connected_to_selected,
                    # Identity of this line for arrowhead settings: path + input/output pair
                    "path": path,
                    "in_name": in_name,
                    "out_name": out_name,
                    "on_route": on_route,
                    "also_needed": also_needed,
                    # Draw route lines last so they sit on top of dashed/dimmed lines
                    "rank": (
                        (2 if on_route else (1 if also_needed else 0))
                        if routes_active
                        else (1 if connected_to_selected else 0)
                    ),
                }
                raw_edges.append(edge)
                pair_key = tuple(sorted((src_key, dst_key)))
                pair_buckets.setdefault(pair_key, []).append(edge)

    for bucket in pair_buckets.values():
        count = len(bucket)
        for idx, edge in enumerate(bucket):
            edge["offset_index"] = idx - (count - 1) / 2.0

    # Draw dimmed/unselected lines first so highlighted lines sit cleanly on top of other lines
    ordered_edges = sorted(raw_edges, key=lambda e: e.get("rank", 0))

    def record_endpoints(edge, sx, sy, ex, ey):
        # Remember where each end landed on screen so clicks/hovers can find it
        if edge_sink is not None:
            edge_sink.append(
                {
                    "path": edge["path"],
                    "in_name": edge["in_name"],
                    "out_name": edge["out_name"],
                    "start": (sx, sy),
                    "finish": (ex, ey),
                }
            )

    for edge in ordered_edges:
        src = edge["src"]
        dst = edge["dst"]

        # Cull lines that cannot be seen: skip only when neither endpoint is
        # visible AND the centre-to-centre segment misses the viewport rect
        if view_rect is not None and not (
            node_intersects_rect(src, view_rect)
            or node_intersects_rect(dst, view_rect)
            or segment_intersects_rect(src["x"], src["y"], dst["x"], dst["y"], *view_rect)
        ):
            continue

        # Each end can independently show an arrowhead; default is finish-only
        arrow_cfg = get_edge_arrows(edge["path"], edge["in_name"], edge["out_name"])
        if arrow_cfg["start"] and arrow_cfg["finish"]:
            arrow_mode = tk.BOTH
        elif arrow_cfg["start"]:
            arrow_mode = tk.FIRST
        elif arrow_cfg["finish"]:
            arrow_mode = tk.LAST
        else:
            arrow_mode = tk.NONE

        if routes_active:
            if edge["on_route"]:
                # Route line: thicker, keeping the line's method colour
                line_color = edge["color"]
                base_lw = ROUTE_LINE_WIDTH
                base_arrow = (14, 17, 7)
                dash = ()
            elif edge["also_needed"]:
                # Required by a route recipe but not part of the route itself:
                # dashed bright line (dash in screen pixels, scaled by zoom)
                line_color = ROUTE_HIGHLIGHT_COLOR
                base_lw = ROUTE_LINE_WIDTH
                base_arrow = (14, 17, 7)
                dash = (max(2, int(round(7 * zoom))), max(2, int(round(5 * zoom))))
            else:
                # Everything not on a route dims toward the background
                line_color = blend_colors(edge["color"], BG_COLOR, DIM_BLEND_FACTOR)
                base_lw = LINE_WIDTH_DIMMED
                base_arrow = (9, 11, 4)
                dash = ()
        elif selected_key is None:
            line_color = edge["color"]
            base_lw = LINE_WIDTH_NORMAL
            base_arrow = (11, 13, 5)
            dash = ()
        elif edge["connected"]:
            line_color = edge["color"]
            base_lw = LINE_WIDTH_SELECTED
            base_arrow = (13, 16, 6)
            dash = ()
        else:
            line_color = blend_colors(edge["color"], BG_COLOR, DIM_BLEND_FACTOR)
            base_lw = LINE_WIDTH_DIMMED
            base_arrow = (9, 11, 4)
            dash = ()

        line_width = max(1.0, base_lw * zoom)
        arrow_shape = (
            max(4, int(round(base_arrow[0] * zoom))),
            max(5, int(round(base_arrow[1] * zoom))),
            max(2, int(round(base_arrow[2] * zoom))),
        )

        x1 = src["x"] * zoom + pan_x
        y1 = src["y"] * zoom + pan_y
        x2 = dst["x"] * zoom + pan_x
        y2 = dst["y"] * zoom + pan_y

        # Half sizes are the node's current (connection-scaled) world size,
        # so lines attach to the node's edge, not its centre
        sw = (src.get("width", src.get("base_width", NODE_MIN_W)) * zoom) / 2.0
        sh = (src.get("height", src.get("base_height", NODE_MIN_H)) * zoom) / 2.0
        dw = (dst.get("width", dst.get("base_width", NODE_MIN_W)) * zoom) / 2.0
        dh = (dst.get("height", dst.get("base_height", NODE_MIN_H)) * zoom) / 2.0

        # Self-loop fallback if an item is both input and output of the same path
        if src is dst:
            loop_r = (28 + abs(edge["offset_index"]) * 10) * zoom * math.sqrt(
                src.get("scale") or NODE_SCALE_MIN
            )
            sx = x1 + sw * 0.5
            sy = y1 - sh
            ex = x1 - sw * 0.5
            ey = y1 - sh
            record_endpoints(edge, sx, sy, ex, ey)
            canvas.create_line(
                sx,
                sy,
                sx + loop_r,
                sy - loop_r,
                ex - loop_r,
                ey - loop_r,
                ex,
                ey,
                smooth=True,
                splinesteps=20,
                fill=line_color,
                width=line_width,
                arrow=arrow_mode,
                arrowshape=arrow_shape,
                dash=dash,
                tags=("connection",),
            )
            continue

        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1e-3:
            continue

        ux = dx / dist
        uy = dy / dist

        # Canonical perpendicular so A->B and B->A curve to opposite sides instead of overlapping
        if edge["src_key"] < edge["dst_key"]:
            px, py = -uy, ux
        else:
            px, py = uy, -ux

        curve_offset = edge["offset_index"] * 26.0 * zoom
        start_pad = 2.0 * zoom
        end_pad = 4.0 * zoom

        if abs(curve_offset) < 1e-3:
            sx, sy = rect_border_point(x1, y1, sw, sh, ux, uy, pad=start_pad)
            ex, ey = rect_border_point(x2, y2, dw, dh, -ux, -uy, pad=end_pad)
            record_endpoints(edge, sx, sy, ex, ey)
            if edge["on_route"]:
                # Bright casing underneath the thicker method-coloured route line
                canvas.create_line(
                    sx,
                    sy,
                    ex,
                    ey,
                    fill=ROUTE_HIGHLIGHT_COLOR,
                    width=max(1.0, (base_lw + ROUTE_CASING_EXTRA) * zoom),
                    capstyle=tk.ROUND,
                    tags=("connection",),
                )
            canvas.create_line(
                sx,
                sy,
                ex,
                ey,
                fill=line_color,
                width=line_width,
                arrow=arrow_mode,
                arrowshape=arrow_shape,
                capstyle=tk.ROUND,
                dash=dash,
                tags=("connection",),
            )
        else:
            mx = (x1 + x2) / 2.0 + px * curve_offset
            my = (y1 + y2) / 2.0 + py * curve_offset

            s_dx, s_dy = mx - x1, my - y1
            s_len = math.hypot(s_dx, s_dy) or 1.0
            sx, sy = rect_border_point(x1, y1, sw, sh, s_dx / s_len, s_dy / s_len, pad=start_pad)

            e_dx, e_dy = mx - x2, my - y2
            e_len = math.hypot(e_dx, e_dy) or 1.0
            ex, ey = rect_border_point(x2, y2, dw, dh, e_dx / e_len, e_dy / e_len, pad=end_pad)

            record_endpoints(edge, sx, sy, ex, ey)
            if edge["on_route"]:
                # Bright casing underneath the thicker method-coloured route line
                canvas.create_line(
                    sx,
                    sy,
                    mx,
                    my,
                    ex,
                    ey,
                    smooth=True,
                    splinesteps=20,
                    fill=ROUTE_HIGHLIGHT_COLOR,
                    width=max(1.0, (base_lw + ROUTE_CASING_EXTRA) * zoom),
                    capstyle=tk.ROUND,
                    tags=("connection",),
                )
            canvas.create_line(
                sx,
                sy,
                mx,
                my,
                ex,
                ey,
                smooth=True,
                splinesteps=20,
                fill=line_color,
                width=line_width,
                arrow=arrow_mode,
                arrowshape=arrow_shape,
                capstyle=tk.ROUND,
                dash=dash,
                tags=("connection",),
            )

    if canvas.find_withtag("node"):
        canvas.tag_lower("connection", "node")


def update_node_selection_visuals(canvas, nodes, selected_node, zoom=1.0,
                                 route_node_keys=None, routes_active=False):
    for node in nodes:
        rect_id = node.get("rect_id")
        if not rect_id:
            continue
        key = node["name"].strip().lower()
        highlighted = bool(routes_active and route_node_keys and key in route_node_keys)
        is_selected = (node is selected_node) and not highlighted
        if highlighted:
            outline_w = max(1.5, ROUTE_OUTLINE_WIDTH * zoom)
            outline_color = ROUTE_HIGHLIGHT_COLOR
        elif is_selected:
            outline_w = max(1.0, 2.5 * zoom)
            outline_color = NODE_SELECTED_OUTLINE
        elif is_liquid(node):
            # Liquids keep their blue outline even when not selected
            outline_w = max(1.0, 2.0 * zoom)
            outline_color = LIQUID_OUTLINE_COLOR
        else:
            outline_w = max(1.0, 2.0 * zoom)
            outline_color = NODE_OUTLINE
        fill_color = node_fill_color(node)
        text_color = best_text_color_for(fill_color)
        if (routes_active and not highlighted) or (
            not routes_active and selected_node is not None and not is_selected
        ):
            # Dimmed nodes blend toward the background, like the dimmed lines
            fill_color = dimmed_toward_background(fill_color)
            text_color = dimmed_toward_background(text_color)
        canvas.itemconfigure(
            rect_id,
            fill=fill_color,
            outline=outline_color,
            width=outline_w,
        )
        text_id = node.get("text_id")
        if text_id:
            canvas.itemconfigure(text_id, fill=text_color)


def redraw_all(
    canvas,
    nodes,
    paths=None,
    method_colors=None,
    selected_node=None,
    zoom=1.0,
    pan_x=0.0,
    pan_y=0.0,
    view_w=None,
    view_h=None,
    edge_sink=None,
    route_node_keys=None,
    route_point_keys=None,
    route_edge_keys=None,
    route_also_keys=None,
    routes_active=False,
):
    """Redraw the scene, creating canvas items only for what is on screen.

    The canvas itself is infinite: there is no scrollregion and no fixed
    bounds, so panning/zooming never hit an edge. view_rect (world coords,
    already including a margin) decides what gets drawn; when the canvas has
    not been mapped yet (size <= 1) everything is drawn.
    """
    canvas.delete("node")
    if view_w is None:
        view_w = canvas.winfo_width()
    if view_h is None:
        view_h = canvas.winfo_height()
    view_rect = None
    if view_w > 1 and view_h > 1:
        view_rect = visible_world_rect(view_w, view_h, zoom, pan_x, pan_y)

    for idx, node in enumerate(nodes):
        if view_rect is not None and not node_intersects_rect(node, view_rect):
            # Off-screen: draw nothing, leave no canvas items behind
            node["rect_id"] = None
            node["text_id"] = None
            node["ring_id"] = None
            continue
        tag = node.get("tag") or f"node_{idx + 1}"
        key = node["name"].strip().lower()
        ring = bool(route_point_keys and key in route_point_keys)
        highlighted = bool(routes_active and route_node_keys and key in route_node_keys)
        if routes_active:
            # Route highlight mode: nodes on a route stay bright, everything else dims
            dimmed = not highlighted
        else:
            highlighted = False
            dimmed = selected_node is not None and node is not selected_node
        draw_node(
            canvas,
            node,
            tag,
            selected=(node is selected_node),
            zoom=zoom,
            pan_x=pan_x,
            pan_y=pan_y,
            dimmed=dimmed,
            ring=ring,
            highlighted=highlighted,
        )
    if paths is not None and method_colors is not None:
        draw_connections(
            canvas,
            nodes,
            paths,
            method_colors,
            selected_node=selected_node,
            zoom=zoom,
            pan_x=pan_x,
            pan_y=pan_y,
            view_rect=view_rect,
            edge_sink=edge_sink,
            route_edge_keys=route_edge_keys,
            route_also_keys=route_also_keys,
            routes_active=routes_active,
        )


class CreateItemTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Create Mod Item Tracker")
        self.root.geometry("1180x760")
        self.root.configure(bg=BG_COLOR)

        self.nodes = []
        self.paths = []
        self.method_colors = {}
        self.next_id = 1

        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

        self.drag_state = {
            "mode": None,  # "node" or "pan"
            "node": None,
            "start_x": 0,
            "start_y": 0,
            "last_x": 0,
            "last_y": 0,
            "dragging": False,
        }
        self.context_node = None
        self.selected_node = None
        self.form_visible = False
        self.editing_path = None  # path currently open in the form for editing (None = adding new)
        self.search_matches = []
        self._redraw_pending = False
        self._drawn_edges = []  # drawn lines with their screen-space end points
        self._last_mouse = None
        self._hovering_end = False

        # Route finding (Shift+click two nodes): endpoints, found routes, highlight sets
        self.route_start = None
        self.route_end = None
        self.route_directions = []  # [(from_name, to_name, routes)] for both directions
        self.routes = []  # every found route of both directions (for highlighting)
        self.route_limit_hit = False
        self._route_node_keys = set()
        self._route_edge_keys = set()
        self._route_also_edge_keys = set()  # extra required input lines, drawn dashed bright
        self._route_point_keys = set()
        self._status_after_id = None

        self._build_ui()
        self._load_initial_state()

    def _build_ui(self):
        self.topbar = tk.Frame(self.root, bg=TOPBAR_BG, padx=12, pady=10)
        self.topbar.pack(side=tk.TOP, fill=tk.X)

        self.entry = tk.Entry(
            self.topbar,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            width=26,
        )
        self.entry.pack(side=tk.LEFT, ipady=6, padx=(0, 8))
        self.entry.bind("<Return>", lambda _event: self.add_item())

        add_btn = tk.Button(
            self.topbar,
            text="Add item",
            command=self.add_item,
            bg=BTN_BG,
            fg=BTN_FG,
            activebackground=BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=14,
            pady=6,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        add_btn.pack(side=tk.LEFT)

        sep = tk.Frame(self.topbar, bg=PANEL_BORDER, width=1, height=26)
        sep.pack(side=tk.LEFT, padx=14)

        search_lbl = tk.Label(
            self.topbar,
            text="Search:",
            bg=TOPBAR_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 10, "bold"),
        )
        search_lbl.pack(side=tk.LEFT, padx=(0, 6))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.topbar,
            textvariable=self.search_var,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            width=24,
        )
        self.search_entry.pack(side=tk.LEFT, ipady=6, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_key_release)
        self.search_entry.bind("<Down>", self._on_search_arrow_down)
        self.search_entry.bind("<Up>", self._on_search_arrow_up)
        self.search_entry.bind("<Return>", self._on_search_return)
        self.search_entry.bind("<Escape>", lambda _e: self.hide_search_dropdown())
        self.search_entry.bind("<FocusIn>", lambda _e: self.update_search_dropdown())

        reset_view_btn = tk.Button(
            self.topbar,
            text="Reset view",
            command=self.reset_view,
            bg=SECONDARY_BTN_BG,
            fg=INPUT_FG,
            activebackground=SECONDARY_BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=12,
            pady=6,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )
        reset_view_btn.pack(side=tk.RIGHT)

        self.main_area = tk.Frame(self.root, bg=BG_COLOR)
        self.main_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._build_side_panel()

        self.canvas = tk.Canvas(
            self.main_area,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_legend()
        self._build_search_dropdown()

        self.context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=TOPBAR_BG,
            fg=INPUT_FG,
            activebackground=BTN_BG,
            activeforeground=BTN_FG,
        )
        self.context_menu.add_command(label="Rename...", command=self.rename_context_node)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.delete_context_node)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Change colour", command=self.change_context_node_color)
        self.context_menu.add_command(label="Reset colour", command=self.reset_context_node_color)

        self.canvas.bind("<ButtonPress-1>", self.on_left_press)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)

        # Window/canvas resize changes the visible viewport, so re-cull and redraw
        self.canvas.bind("<Configure>", lambda _e: self._schedule_redraw())

        # Mouse wheel zoom (Windows/macOS <MouseWheel>, Linux X11 <Button-4>/<Button-5>)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel_up)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel_down)

        # Support right-click across Windows/Linux (<Button-3>) and macOS (<Button-2> / Ctrl-Click)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click)
        self.canvas.bind("<ButtonPress-2>", self.on_right_click)
        self.canvas.bind("<Control-Button-1>", self.on_right_click)

        # Escape clears any active route selection and highlighting
        self.root.bind("<Escape>", self._on_escape_key, add="+")

        # Small status message overlaid at the bottom-left of the canvas
        self.status_label = tk.Label(
            self.canvas,
            text="",
            bg=TOPBAR_BG,
            fg=NODE_TEXT,
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=5,
            highlightbackground=PANEL_BORDER,
            highlightthickness=1,
        )

        # Dismiss search dropdown when clicking outside search widgets
        self.root.bind("<ButtonPress-1>", self._on_global_click, add="+")
        self.root.bind("<Configure>", lambda _e: self._reposition_search_dropdown(), add="+")

        # Mouse-wheel scrolling for the right panel: when the pointer is over
        # the side panel, the wheel scrolls the paths list (path cards plus the
        # "Made from"/"Used in" sections below them) instead of zooming the canvas
        self.root.bind_all("<MouseWheel>", self._on_panel_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_panel_wheel_up, add="+")
        self.root.bind_all("<Button-5>", self._on_panel_wheel_down, add="+")

    def _build_search_dropdown(self):
        self.search_dropdown = tk.Frame(
            self.root,
            bg=CARD_BG,
            highlightbackground=PANEL_BORDER,
            highlightthickness=1,
        )
        self.search_listbox = tk.Listbox(
            self.search_dropdown,
            bg=CARD_BG,
            fg=NODE_TEXT,
            selectbackground=BTN_BG,
            selectforeground=BTN_FG,
            activestyle="none",
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            exportselection=False,
            cursor="hand2",
        )
        self.search_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.search_listbox.bind("<ButtonRelease-1>", self._on_search_listbox_click)
        self.search_listbox.bind("<Return>", self._on_search_return)
        self.search_listbox.bind("<Escape>", lambda _e: self.hide_search_dropdown())

    def _build_legend(self):
        self.legend_frame = tk.Frame(
            self.canvas,
            bg=PANEL_BG,
            padx=10,
            pady=8,
            highlightbackground=PANEL_BORDER,
            highlightthickness=1,
        )
        self.legend_title = tk.Label(
            self.legend_frame,
            text="Methods",
            bg=PANEL_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.legend_title.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))

        self.legend_items_frame = tk.Frame(self.legend_frame, bg=PANEL_BG)
        self.legend_items_frame.pack(side=tk.TOP, fill=tk.BOTH)

    def _build_side_panel(self):
        self.side_panel = tk.Frame(
            self.main_area,
            bg=PANEL_BG,
            width=PANEL_WIDTH,
            highlightbackground=PANEL_BORDER,
            highlightthickness=1,
        )
        self.side_panel.pack_propagate(False)

        header = tk.Frame(self.side_panel, bg=PANEL_BG, padx=14, pady=12)
        header.pack(side=tk.TOP, fill=tk.X)

        self.panel_title_label = tk.Label(
            header,
            text="",
            bg=PANEL_BG,
            fg=NODE_TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=PANEL_WIDTH - 70,
        )
        self.panel_title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        close_btn = tk.Button(
            header,
            text="\u2715",
            command=self.close_side_panel,
            bg=SECONDARY_BTN_BG,
            fg=INPUT_FG,
            activebackground=SECONDARY_BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        close_btn.pack(side=tk.RIGHT)

        rename_btn = tk.Button(
            header,
            text="Rename",
            command=self.rename_selected_node,
            bg=SECONDARY_BTN_BG,
            fg=INPUT_FG,
            activebackground=SECONDARY_BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=8,
            pady=2,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        rename_btn.pack(side=tk.RIGHT, padx=(0, 8))

        divider = tk.Frame(self.side_panel, bg=PANEL_BORDER, height=1)
        divider.pack(side=tk.TOP, fill=tk.X)

        # Item type dropdown (shown under the item's name while an item is selected)
        self.type_row = tk.Frame(self.side_panel, bg=PANEL_BG, padx=14, pady=6)
        tk.Label(
            self.type_row,
            text="Type:",
            bg=PANEL_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.type_var = tk.StringVar(value="Item")
        self.type_menu = tk.OptionMenu(
            self.type_row, self.type_var, "Item", "Liquid", command=self.on_item_type_change
        )
        self.type_menu.configure(
            bg=INPUT_BG,
            fg=INPUT_FG,
            activebackground=SECONDARY_BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            highlightthickness=0,
            relief=tk.FLAT,
            bd=0,
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        self.type_menu["menu"].configure(
            bg=CARD_BG, fg=NODE_TEXT, activebackground=BTN_BG, activeforeground=BTN_FG
        )
        self.type_menu.pack(side=tk.LEFT)

        self.actions_bar = tk.Frame(self.side_panel, bg=PANEL_BG, padx=14, pady=10)
        self.actions_bar.pack(side=tk.TOP, fill=tk.X)

        paths_heading = tk.Label(
            self.actions_bar,
            text="Paths",
            bg=PANEL_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 10, "bold"),
        )
        paths_heading.pack(side=tk.LEFT)

        self.add_path_btn = tk.Button(
            self.actions_bar,
            text="Add path",
            command=self.open_add_path_form,
            bg=BTN_BG,
            fg=BTN_FG,
            activebackground=BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.add_path_btn.pack(side=tk.RIGHT)

        # Collapsible "Add path" form
        self.form_frame = tk.Frame(
            self.side_panel,
            bg=CARD_BG,
            padx=12,
            pady=10,
            highlightbackground=PANEL_BORDER,
            highlightthickness=1,
        )

        tk.Label(
            self.form_frame,
            text="Method",
            bg=CARD_BG,
            fg=INPUT_FG,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(side=tk.TOP, fill=tk.X)
        self.method_entry = tk.Entry(
            self.form_frame,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.method_entry.pack(side=tk.TOP, fill=tk.X, ipady=4, pady=(2, 8))

        tk.Label(
            self.form_frame,
            text="Inputs (comma-separated)",
            bg=CARD_BG,
            fg=INPUT_FG,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(side=tk.TOP, fill=tk.X)
        self.inputs_entry = tk.Entry(
            self.form_frame,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.inputs_entry.pack(side=tk.TOP, fill=tk.X, ipady=4, pady=(2, 2))
        self.inputs_hint_text = (
            'Amount before the name, e.g. "3 Clay, 1 Flint, 50 Lava" '
            '("3x Clay" also works; no number = 1)'
        )
        self.inputs_hint = tk.Label(
            self.form_frame,
            text=self.inputs_hint_text,
            bg=CARD_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 8),
            anchor="w",
            justify=tk.LEFT,
        )
        self.inputs_hint.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        tk.Label(
            self.form_frame,
            text="Outputs (comma-separated)",
            bg=CARD_BG,
            fg=INPUT_FG,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(side=tk.TOP, fill=tk.X)
        self.outputs_entry = tk.Entry(
            self.form_frame,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 10),
        )
        self.outputs_entry.pack(side=tk.TOP, fill=tk.X, ipady=4, pady=(2, 2))
        self.outputs_hint_text = (
            'Amount before the name, chance after it, e.g. "1 Veridium, 2 Gravel, 1 Flint 25%" '
            "(amount default 1, chance default 100%)"
        )
        self.outputs_hint = tk.Label(
            self.form_frame,
            text=self.outputs_hint_text,
            bg=CARD_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 8),
            anchor="w",
            justify=tk.LEFT,
        )
        self.outputs_hint.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        self.method_entry.bind("<Return>", lambda _event: self.inputs_entry.focus_set())
        self.inputs_entry.bind("<Return>", lambda _event: self.outputs_entry.focus_set())
        self.outputs_entry.bind("<Return>", lambda _event: self.submit_add_path_form())

        form_btns = tk.Frame(self.form_frame, bg=CARD_BG)
        form_btns.pack(side=tk.TOP, fill=tk.X)

        self.save_path_btn = tk.Button(
            form_btns,
            text="Save path",
            command=self.submit_add_path_form,
            bg=BTN_BG,
            fg=BTN_FG,
            activebackground=BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        )
        self.save_path_btn.pack(side=tk.LEFT)

        cancel_path_btn = tk.Button(
            form_btns,
            text="Cancel",
            command=self.hide_add_path_form,
            bg=SECONDARY_BTN_BG,
            fg=INPUT_FG,
            activebackground=SECONDARY_BTN_ACTIVE_BG,
            activeforeground=BTN_FG,
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=4,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        cancel_path_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Scrollable list container for paths
        self.paths_container = tk.Frame(self.side_panel, bg=PANEL_BG)
        self.paths_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=14, pady=(0, 12))

        self.paths_canvas = tk.Canvas(
            self.paths_container,
            bg=PANEL_BG,
            highlightthickness=0,
        )
        self.paths_scrollbar = tk.Scrollbar(
            self.paths_container,
            orient=tk.VERTICAL,
            command=self.paths_canvas.yview,
        )
        self.paths_list_frame = tk.Frame(self.paths_canvas, bg=PANEL_BG)

        self.paths_list_window = self.paths_canvas.create_window(
            (0, 0),
            window=self.paths_list_frame,
            anchor="nw",
            width=PANEL_WIDTH - 48,
        )
        self.paths_canvas.configure(yscrollcommand=self.paths_scrollbar.set)

        self.paths_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.paths_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.paths_list_frame.bind("<Configure>", self._on_paths_frame_configure)
        self.paths_canvas.bind("<Configure>", self._on_paths_canvas_configure)

        # "Made from" / "Used in" sections live INSIDE the scrollable paths list,
        # directly below the path cards, so they scroll along with the paths and
        # stay reachable no matter how many paths there are.
        # (constructor pady must be a single distance; the per-section bottom
        # padding is applied at pack time in _fill_section)
        self.made_from_frame = tk.Frame(self.paths_list_frame, bg=PANEL_BG, padx=4, pady=0)
        self.used_in_frame = tk.Frame(self.paths_list_frame, bg=PANEL_BG, padx=4, pady=0)

    def _clear_section(self, frame):
        for child in frame.winfo_children():
            child.destroy()
        if frame.winfo_ismapped():
            frame.pack_forget()

    def _clear_path_list_children(self):
        """Destroy the path/route cards but keep the two section frames as
        children of the list (they are re-packed below the cards afterwards,
        so the whole list scrolls as one unit)."""
        for child in self.paths_list_frame.winfo_children():
            if child is self.made_from_frame or child is self.used_in_frame:
                continue
            child.destroy()
        self._clear_section(self.made_from_frame)
        self._clear_section(self.used_in_frame)

    def _fill_section(self, frame, heading, lines, pad_bottom=4):
        """Render one side-panel section (heading + one line per entry)."""
        self._clear_section(frame)
        if not lines:
            return
        frame.pack(side=tk.TOP, fill=tk.X, pady=(0, pad_bottom))
        tk.Label(
            frame,
            text=heading,
            bg=PANEL_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(side=tk.TOP, fill=tk.X)
        for line in lines:
            tk.Label(
                frame,
                text=line,
                bg=PANEL_BG,
                fg=NODE_TEXT,
                font=("Segoe UI", 9),
                anchor="w",
                justify=tk.LEFT,
                wraplength=PANEL_WIDTH - 60,
            ).pack(side=tk.TOP, fill=tk.X, pady=(2, 0))

    def _render_item_sections(self, item_name):
        """'Made from' (paths producing the item) and 'Used in' (paths consuming it)."""
        node_by_key = {n["name"].strip().lower(): n for n in self.nodes}
        target = item_name.strip().lower()
        made_from = []
        used_in = []
        for p in self.paths:
            inputs = p.get("inputs", [])
            outputs = p.get("outputs", [])
            in_inputs = any(str(n).strip().lower() == target for n in inputs)
            in_outputs = any(str(n).strip().lower() == target for n in outputs)
            inputs_str = ", ".join(
                format_amount(input_amount(p, n), n, node_by_key) for n in inputs
            )
            outputs_str = ", ".join(
                format_amount(output_amount(p, n), n, node_by_key) for n in outputs
            )
            if in_outputs:
                made_from.append(f"{p['method']}: needs {inputs_str}")
            if in_inputs:
                used_in.append(f"{p['method']}: uses {inputs_str}, makes {outputs_str}")
        self._fill_section(self.made_from_frame, "Made from", made_from, pad_bottom=4)
        self._fill_section(self.used_in_frame, "Used in", used_in, pad_bottom=12)

    def _on_paths_frame_configure(self, _event=None):
        bbox = self.paths_canvas.bbox("all")
        self.paths_canvas.configure(scrollregion=bbox if bbox else (0, 0, 0, 0))

    def _on_paths_canvas_configure(self, event):
        if event.width > 1:
            self.paths_canvas.itemconfigure(self.paths_list_window, width=event.width)
            bbox = self.paths_canvas.bbox("all")
            self.paths_canvas.configure(scrollregion=bbox if bbox else (0, 0, 0, 0))

    def _sync_paths_scrollregion(self):
        self.root.update_idletasks()
        canvas_w = self.paths_canvas.winfo_width()
        if canvas_w <= 1:
            canvas_w = PANEL_WIDTH - 48
        self.paths_canvas.itemconfigure(self.paths_list_window, width=canvas_w)
        self.paths_list_frame.update_idletasks()
        bbox = self.paths_canvas.bbox("all")
        self.paths_canvas.configure(scrollregion=bbox if bbox else (0, 0, 0, 0))

    def screen_to_world(self, sx, sy):
        return (sx - self.pan_x) / self.zoom, (sy - self.pan_y) / self.zoom

    def world_to_screen(self, wx, wy):
        return wx * self.zoom + self.pan_x, wy * self.zoom + self.pan_y

    def _recalculate_sizes(self):
        # Node sizes depend only on the current paths, so recompute them on
        # every redraw: adding/deleting a path resizes nodes immediately
        recalculate_node_sizes(self.canvas, self.nodes, self.paths)

    def _current_view_rect(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w <= 1 or h <= 1:
            return None  # canvas not mapped yet: draw everything
        return visible_world_rect(w, h, self.zoom, self.pan_x, self.pan_y)

    def _route_draw_kwargs(self):
        return {
            "route_node_keys": self._route_node_keys,
            "route_point_keys": self._route_point_keys,
            "route_edge_keys": self._route_edge_keys,
            "route_also_keys": self._route_also_edge_keys,
            "routes_active": bool(self.routes),
        }

    def _node_visual_kwargs(self):
        return {
            "route_node_keys": self._route_node_keys,
            "routes_active": bool(self.routes),
        }

    def _redraw_scene(self):
        self._recalculate_sizes()
        redraw_all(
            self.canvas,
            self.nodes,
            self.paths,
            self.method_colors,
            selected_node=self.selected_node,
            zoom=self.zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
            edge_sink=self._drawn_edges,
            **self._route_draw_kwargs(),
        )
        self._update_hover()

    def _redraw_lines(self):
        draw_connections(
            self.canvas,
            self.nodes,
            self.paths,
            self.method_colors,
            selected_node=self.selected_node,
            zoom=self.zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
            view_rect=self._current_view_rect(),
            edge_sink=self._drawn_edges,
            route_edge_keys=self._route_edge_keys,
            route_also_keys=self._route_also_edge_keys,
            routes_active=bool(self.routes),
        )
        self._update_hover()

    def _schedule_redraw(self):
        # Coalesce bursts of pan/drag/resize events into one redraw per idle cycle
        if self._redraw_pending:
            return
        self._redraw_pending = True
        try:
            self.canvas.after_idle(self._run_scheduled_redraw)
        except tk.TclError:
            self._redraw_pending = False

    def _run_scheduled_redraw(self):
        self._redraw_pending = False
        self._redraw_scene()

    # --- Route finding: Shift+click two nodes to highlight every route between them ---

    def show_status(self, message, auto_hide_ms=6000):
        """Small status message overlaid at the bottom-left of the canvas."""
        self.status_label.configure(text=message)
        self.status_label.place(relx=0.0, rely=1.0, x=14, y=-12, anchor="sw")
        self.status_label.lift()
        if self._status_after_id is not None:
            try:
                self.root.after_cancel(self._status_after_id)
            except tk.TclError:
                pass
        self._status_after_id = None
        if auto_hide_ms:
            self._status_after_id = self.root.after(auto_hide_ms, self.hide_status)

    def hide_status(self):
        self._status_after_id = None
        self.status_label.place_forget()

    def _on_escape_key(self, _event=None):
        if self.route_start is not None or self.routes:
            self.clear_route_selection()

    def _on_shift_click_node(self, node):
        """Shift+click marks route endpoints. It never drags the node and never
        opens the node's normal side panel."""
        if self.route_start is not None and self.route_end is not None:
            # Shift+click on a third node: start a new selection with it as the first point
            self.route_start = node
            self.route_end = None
            self.route_directions = []
            self.routes = []
            self.route_limit_hit = False
            self._route_also_edge_keys = set()
            self.show_status(
                f"Route start: {node['name']} — Shift+click a second node",
                auto_hide_ms=4000,
            )
        elif self.route_start is None:
            self.route_start = node
            self.show_status(
                f"Route start: {node['name']} — Shift+click a second node",
                auto_hide_ms=4000,
            )
        elif node is self.route_start:
            return  # clicking the first point again changes nothing
        else:
            self.route_end = node
            self._compute_routes()
        self._after_route_change()

    def _compute_routes(self):
        a = self.route_start["name"]
        b = self.route_end["name"]
        # Both directions are searched, each following arrowheads only
        self.route_directions, self.route_limit_hit = find_routes(self.paths, a, b)
        self.routes = [
            route for (_fa, _fb, routes) in self.route_directions for route in routes
        ]
        found = [
            f"{len(routes)} route(s) {fa} \u2192 {fb}"
            for fa, fb, routes in self.route_directions
            if routes
        ]
        if found:
            msg = "Found " + " and ".join(found)
            if self.route_limit_hit:
                msg += (
                    f" (limit hit: max {ROUTE_MAX_ROUTES} routes per direction, "
                    f"{ROUTE_MAX_STEPS} steps each)"
                )
            self.show_status(msg)
        else:
            self.show_status(
                f"No route found between {a} and {b}", auto_hide_ms=8000
            )

    def _after_route_change(self):
        self._route_node_keys = set()
        self._route_edge_keys = set()
        self._route_also_edge_keys = set()
        for route in self.routes:
            self._route_node_keys.add(_name_key(route[0]["src"]))
            for step in route:
                self._route_node_keys.add(_name_key(step["dst"]))
                self._route_edge_keys.add(
                    _route_edge_key(step["path"], step["in_name"], step["out_name"])
                )
                # Extra required inputs of this recipe become dashed bright lines
                for also in step_also_inputs(step):
                    self._route_also_edge_keys.add(
                        _route_edge_key(step["path"], also, step["out_name"])
                    )
        self._route_point_keys = set()
        if self.route_start is not None:
            self._route_point_keys.add(_name_key(self.route_start["name"]))
        if self.route_end is not None:
            self._route_point_keys.add(_name_key(self.route_end["name"]))
        # The routes list lives in the side panel once both points are marked
        if self.route_end is not None and not self.side_panel.winfo_ismapped():
            self.side_panel.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)
        if self.side_panel.winfo_ismapped():
            self._render_route_panel()
        self._redraw_scene()

    def clear_route_selection(self, redraw=True):
        had_routes = self.route_start is not None or bool(self.routes)
        self.route_start = None
        self.route_end = None
        self.route_directions = []
        self.routes = []
        self.route_limit_hit = False
        self._route_node_keys = set()
        self._route_edge_keys = set()
        self._route_also_edge_keys = set()
        self._route_point_keys = set()
        self.hide_status()
        if self.side_panel.winfo_ismapped():
            if self.selected_node is None:
                self.side_panel.pack_forget()
            else:
                self.refresh_side_panel_paths()
        if had_routes and redraw:
            self._redraw_scene()

    def _refresh_routes_after_edit(self):
        """Paths changed while a route selection is active: recompute the routes."""
        if self.route_start is not None and self.route_end is not None:
            self._compute_routes()
            self._after_route_change()

    def _render_route_panel(self):
        self._clear_path_list_children()
        self.hide_add_path_form()
        self._sync_type_row()
        if self.route_start is not None and self.route_end is not None:
            self.panel_title_label.configure(
                text=f"Routes between {self.route_start['name']} and {self.route_end['name']}"
            )
        elif self.route_start is not None:
            self.panel_title_label.configure(text=f"Route from {self.route_start['name']}")
        else:
            self.panel_title_label.configure(text="")
        if self.route_start is None:
            self._sync_paths_scrollregion()
            return
        node_by_key = {n["name"].strip().lower(): n for n in self.nodes}
        if self.route_end is None:
            hint = tk.Label(
                self.paths_list_frame,
                text="Shift+click a second node to find the routes between the two points.",
                bg=PANEL_BG,
                fg=MUTED_FG,
                font=("Segoe UI", 10),
                anchor="w",
                justify=tk.LEFT,
                wraplength=PANEL_WIDTH - 60,
            )
            hint.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
        else:
            # Each direction gets its own heading; a direction with no
            # routes says so under its heading
            for fa, fb, routes in self.route_directions:
                head = tk.Label(
                    self.paths_list_frame,
                    text=f"{fa} \u2192 {fb}",
                    bg=PANEL_BG,
                    fg=NODE_TEXT,
                    font=("Segoe UI", 10, "bold"),
                    anchor="w",
                )
                head.pack(side=tk.TOP, fill=tk.X, pady=(6, 2))
                if not routes:
                    note = tk.Label(
                        self.paths_list_frame,
                        text="No route found in this direction.",
                        bg=PANEL_BG,
                        fg=MUTED_FG,
                        font=("Segoe UI", 10),
                        anchor="w",
                        justify=tk.LEFT,
                        wraplength=PANEL_WIDTH - 60,
                    )
                    note.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
                    continue
                count = tk.Label(
                    self.paths_list_frame,
                    text=f"{len(routes)} route(s):",
                    bg=PANEL_BG,
                    fg=NODE_TEXT,
                    font=("Segoe UI", 10),
                    anchor="w",
                )
                count.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
                for route in routes:
                    card = tk.Frame(
                        self.paths_list_frame,
                        bg=CARD_BG,
                        padx=10,
                        pady=6,
                        highlightbackground=PANEL_BORDER,
                        highlightthickness=1,
                    )
                    card.pack(side=tk.TOP, fill=tk.X, pady=(0, 6))
                    lbl = tk.Label(
                        card,
                        text=format_route(route, node_by_key),
                        bg=CARD_BG,
                        fg=NODE_TEXT,
                        font=("Segoe UI", 9),
                        anchor="w",
                        justify=tk.LEFT,
                        wraplength=PANEL_WIDTH - 90,
                    )
                    lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.paths_canvas.yview_moveto(0)
        self._sync_paths_scrollregion()

    # --- Line-end arrowhead interaction ---

    def _find_edge_end_at(self, sx, sy):
        """Nearest drawn line end within END_HIT_RADIUS_PX of (sx, sy).

        Returns (edge_info, "start"|"finish") or None. The radius is in screen
        pixels, so the click area stays the same usable size at any zoom.
        """
        best = None
        best_d2 = END_HIT_RADIUS_PX ** 2
        for edge in self._drawn_edges:
            for which, pos in (("start", edge["start"]), ("finish", edge["finish"])):
                d2 = (sx - pos[0]) ** 2 + (sy - pos[1]) ** 2
                if d2 <= best_d2:
                    best_d2 = d2
                    best = (edge, which)
        return best

    def _toggle_edge_end(self, edge, which):
        """Flip the arrowhead on one end of a line and persist it."""
        cfg = get_edge_arrows(edge["path"], edge["in_name"], edge["out_name"])
        cfg[which] = not cfg[which]
        set_edge_arrows(edge["path"], edge["in_name"], edge["out_name"], cfg)
        self._save_state()  # saved per path + input/output pair; deleting the path deletes these
        self._redraw_lines()

    def on_canvas_motion(self, event):
        self._last_mouse = (event.x, event.y)
        self._update_hover()

    def _update_hover(self):
        """Hand cursor + a small dot when hovering near a line end."""
        hit = self._find_edge_end_at(*self._last_mouse) if self._last_mouse else None
        if hit is None:
            if self._hovering_end:
                self._hovering_end = False
                self.canvas.configure(cursor="")
            self.canvas.delete("end_hint")
            return
        edge, which = hit
        pos = edge["start"] if which == "start" else edge["finish"]
        self._hovering_end = True
        self.canvas.configure(cursor="hand2")
        self.canvas.delete("end_hint")
        r = END_DOT_RADIUS_PX
        self.canvas.create_oval(
            pos[0] - r,
            pos[1] - r,
            pos[0] + r,
            pos[1] + r,
            fill=END_DOT_COLOR,
            outline="",
            tags=("end_hint",),
        )
        self.canvas.tag_raise("end_hint", "connection")

    def _apply_zoom_at(self, factor, pivot_sx, pivot_sy):
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self.zoom * factor))
        if abs(new_zoom - self.zoom) < 1e-6:
            return
        world_x, world_y = self.screen_to_world(pivot_sx, pivot_sy)
        self.zoom = new_zoom
        self.pan_x = pivot_sx - world_x * self.zoom
        self.pan_y = pivot_sy - world_y * self.zoom
        self._redraw_scene()

    def on_mouse_wheel(self, event):
        if event.delta == 0:
            return
        steps = event.delta / 120.0 if abs(event.delta) >= 120 else (1.0 if event.delta > 0 else -1.0)
        factor = ZOOM_STEP ** steps
        self._apply_zoom_at(factor, event.x, event.y)

    def on_mouse_wheel_up(self, event):
        self._apply_zoom_at(ZOOM_STEP, event.x, event.y)

    def on_mouse_wheel_down(self, event):
        self._apply_zoom_at(1.0 / ZOOM_STEP, event.x, event.y)

    def reset_view(self):
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._redraw_scene()

    def center_view_on_node(self, node):
        self.root.update_idletasks()
        cw = max(self.canvas.winfo_width(), 400)
        ch = max(self.canvas.winfo_height(), 300)
        self.pan_x = cw / 2.0 - node["x"] * self.zoom
        self.pan_y = ch / 2.0 - node["y"] * self.zoom
        self._redraw_scene()

    # --- Search box & dropdown ---

    def _on_search_key_release(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape"):
            return
        self.update_search_dropdown()

    def _reposition_search_dropdown(self):
        if not self.search_dropdown.winfo_ismapped():
            return
        self.root.update_idletasks()
        x = self.search_entry.winfo_rootx() - self.root.winfo_rootx()
        y = (
            self.search_entry.winfo_rooty()
            - self.root.winfo_rooty()
            + self.search_entry.winfo_height()
            + 2
        )
        width = max(self.search_entry.winfo_width(), 200)
        row_h = 22
        visible_rows = min(8, max(1, len(self.search_matches)))
        height = visible_rows * row_h + 6
        self.search_dropdown.place(x=x, y=y, width=width, height=height)
        self.search_dropdown.lift()

    def update_search_dropdown(self):
        query = self.search_var.get().strip().lower()
        if not query:
            self.hide_search_dropdown()
            return

        # Prioritize prefix matches first, then substring matches (both case-insensitive)
        prefix_matches = []
        substring_matches = []
        for node in self.nodes:
            low = node["name"].lower()
            if low.startswith(query):
                prefix_matches.append(node)
            elif query in low:
                substring_matches.append(node)

        self.search_matches = prefix_matches + substring_matches
        if not self.search_matches:
            self.hide_search_dropdown()
            return

        self.search_listbox.delete(0, tk.END)
        for node in self.search_matches:
            self.search_listbox.insert(tk.END, node["name"])
        self.search_listbox.selection_set(0)
        self.search_listbox.activate(0)

        self.search_dropdown.place(x=0, y=0)
        self._reposition_search_dropdown()

    def hide_search_dropdown(self):
        self.search_matches = []
        if self.search_dropdown.winfo_ismapped():
            self.search_dropdown.place_forget()

    def _on_search_arrow_down(self, _event):
        if not self.search_matches:
            self.update_search_dropdown()
            return "break"
        cur = self.search_listbox.curselection()
        idx = (cur[0] + 1) % len(self.search_matches) if cur else 0
        self.search_listbox.selection_clear(0, tk.END)
        self.search_listbox.selection_set(idx)
        self.search_listbox.activate(idx)
        self.search_listbox.see(idx)
        return "break"

    def _on_search_arrow_up(self, _event):
        if not self.search_matches:
            return "break"
        cur = self.search_listbox.curselection()
        idx = (cur[0] - 1) % len(self.search_matches) if cur else len(self.search_matches) - 1
        self.search_listbox.selection_clear(0, tk.END)
        self.search_listbox.selection_set(idx)
        self.search_listbox.activate(idx)
        self.search_listbox.see(idx)
        return "break"

    def _on_search_return(self, _event=None):
        if not self.search_matches:
            query = self.search_var.get().strip()
            if query:
                exact = self._find_node_by_name(query)
                if exact is not None:
                    self._pick_search_node(exact)
            return "break"
        cur = self.search_listbox.curselection()
        idx = cur[0] if cur else 0
        if 0 <= idx < len(self.search_matches):
            self._pick_search_node(self.search_matches[idx])
        return "break"

    def _on_search_listbox_click(self, event):
        if not self.search_matches:
            return
        idx = self.search_listbox.nearest(event.y)
        if 0 <= idx < len(self.search_matches):
            self._pick_search_node(self.search_matches[idx])

    def _pick_search_node(self, node):
        self.search_var.set(node["name"])
        self.hide_search_dropdown()
        self.select_node(node)
        self.center_view_on_node(node)
        self.canvas.focus_set()

    def _on_global_click(self, event):
        if not self.search_dropdown.winfo_ismapped():
            return
        widget = event.widget
        if widget in (self.search_entry, self.search_listbox, self.search_dropdown):
            return
        self.hide_search_dropdown()

    # --- Mouse-wheel scrolling of the right panel's paths list ---

    def _widget_in_side_panel(self, widget):
        w = widget
        while w is not None:
            if w is self.side_panel:
                return True
            try:
                w = w.master
            except tk.TclError:
                return False
        return False

    def _scroll_paths_list(self, steps):
        try:
            self.paths_canvas.yview_scroll(steps, "units")
        except tk.TclError:
            pass

    def _on_panel_mousewheel(self, event):
        if not self._widget_in_side_panel(getattr(event, "widget", None)):
            return None  # not over the side panel: leave canvas zoom etc. alone
        delta = getattr(event, "delta", 0)
        if not delta:
            return "break"
        mag = max(1, abs(delta) // 120) if abs(delta) >= 120 else 1
        self._scroll_paths_list(-mag if delta > 0 else mag)
        return "break"

    def _on_panel_wheel_up(self, event):  # Linux X11 wheel up
        if not self._widget_in_side_panel(getattr(event, "widget", None)):
            return None
        self._scroll_paths_list(-1)
        return "break"

    def _on_panel_wheel_down(self, event):  # Linux X11 wheel down
        if not self._widget_in_side_panel(getattr(event, "widget", None)):
            return None
        self._scroll_paths_list(1)
        return "break"

    # --- Persistence & state ---

    def _load_initial_state(self):
        loaded_nodes, loaded_paths, loaded_colors = load_data()
        self.paths = loaded_paths
        self.method_colors = loaded_colors

        # Positions are plain world coordinates; no canvas size or scroll
        # region is involved, so empty space costs nothing
        for entry in loaded_nodes:
            node = {
                "name": entry["name"],
                "x": entry["x"],
                "y": entry["y"],
                "tag": f"node_{self.next_id}",
            }
            color = _normalize_hex_color(entry.get("color"))
            if color:
                node["color"] = color
            if normalize_node_type(entry.get("type")) == "liquid":
                node["type"] = "liquid"
            self.next_id += 1
            self.nodes.append(node)

        # Ensure any items referenced by existing paths have nodes
        created_missing = False
        for path in self.paths:
            mkey = path["method"].strip().lower()
            if mkey not in self.method_colors:
                self.method_colors[mkey] = pick_next_palette_color(self.method_colors)
            for name in path["inputs"] + path["outputs"]:
                if self._find_node_by_name(name) is None:
                    self._create_node(name)
                    created_missing = True

        self._redraw_scene()
        self.refresh_legend()
        if created_missing:
            self._save_state()

    def _save_state(self):
        # node["x"] and node["y"] are always stored in normal (unzoomed) world coordinates
        save_data(self.nodes, self.paths, self.method_colors)

    def _ensure_method_color(self, method_name):
        key = method_name.strip().lower()
        if key not in self.method_colors:
            self.method_colors[key] = pick_next_palette_color(self.method_colors)
        return self.method_colors[key]

    def _active_methods(self):
        methods = {}
        for path in self.paths:
            raw_name = path["method"].strip()
            key = raw_name.lower()
            if key and key not in methods:
                methods[key] = raw_name
        return methods

    def _canonical_method_name(self, raw_method):
        key = raw_method.strip().lower()
        active = self._active_methods()
        if key in active:
            return active[key]
        return raw_method.strip()

    def refresh_legend(self):
        for child in self.legend_items_frame.winfo_children():
            child.destroy()

        active_methods = self._active_methods()
        if not active_methods:
            self.legend_frame.place_forget()
            return

        for mkey, display_name in active_methods.items():
            color = self._ensure_method_color(display_name)
            row = tk.Frame(self.legend_items_frame, bg=PANEL_BG, pady=2)
            row.pack(side=tk.TOP, fill=tk.X)

            swatch = tk.Canvas(
                row,
                width=16,
                height=16,
                bg=color,
                highlightthickness=1,
                highlightbackground=NODE_TEXT,
                cursor="hand2",
            )
            swatch.pack(side=tk.LEFT, padx=(0, 8))
            swatch.bind(
                "<Button-1>",
                lambda _e, k=mkey, d=display_name: self.change_method_color(k, d),
            )

            lbl = tk.Label(
                row,
                text=display_name,
                bg=PANEL_BG,
                fg=NODE_TEXT,
                font=("Segoe UI", 9),
                anchor="w",
            )
            lbl.pack(side=tk.LEFT, fill=tk.X)

        self.legend_frame.place(x=14, y=14, anchor="nw")
        self.legend_frame.lift()

    def change_method_color(self, method_key, display_name):
        current = self.method_colors.get(method_key, METHOD_PALETTE[0])
        chosen = colorchooser.askcolor(
            color=current,
            title=f"Choose colour for {display_name}",
            parent=self.root,
        )
        if chosen and chosen[1]:
            hex_color = _normalize_hex_color(chosen[1])
            if hex_color:
                self.method_colors[method_key] = hex_color
                self._save_state()
                self._redraw_lines()
                self.refresh_legend()
                if self.selected_node is not None:
                    self.refresh_side_panel_paths()

    def _find_node_by_name(self, name):
        target = name.strip().lower()
        for node in self.nodes:
            if node["name"].strip().lower() == target:
                return node
        return None

    def _find_node_at(self, sx, sy):
        overlapping = self.canvas.find_overlapping(sx, sy, sx, sy)
        for item_id in reversed(overlapping):
            tags = self.canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith("node_"):
                    for node in self.nodes:
                        if node.get("tag") == tag:
                            return node
        return None

    def _estimate_node_size(self, name):
        est_w = max(NODE_MIN_W, len(name) * 9 + NODE_PAD_X * 2)
        est_h = NODE_MIN_H
        return est_w, est_h

    def _overlaps_existing(self, x, y, width, height, margin=24):
        half_w = width / 2.0 + margin
        half_h = height / 2.0 + margin
        for node in self.nodes:
            # "width"/"height" are the current connection-scaled world sizes
            nw = node.get("width", node.get("base_width", NODE_MIN_W)) / 2.0
            nh = node.get("height", node.get("base_height", NODE_MIN_H)) / 2.0
            if abs(x - node["x"]) < (half_w + nw) and abs(y - node["y"]) < (half_h + nh):
                return True
        return False

    def _find_empty_position(self, name, near_node=None):
        self.root.update_idletasks()
        canvas_w = max(self.canvas.winfo_width(), 650)
        canvas_h = max(self.canvas.winfo_height(), 500)
        est_w, est_h = self._estimate_node_size(name)

        # Compute visible world bounds so newly added nodes appear in view at unzoomed world coords
        vis_left, vis_top = self.screen_to_world(0, 0)
        vis_right, vis_bottom = self.screen_to_world(canvas_w, canvas_h)

        min_x = vis_left + est_w / 2.0 + 24
        max_x = max(min_x + 80, vis_right - est_w / 2.0 - 24)
        min_y = vis_top + est_h / 2.0 + 24
        max_y = max(min_y + 80, vis_bottom - est_h / 2.0 - 24)

        if near_node is not None:
            cx, cy = near_node["x"], near_node["y"]
        else:
            cx, cy = self.screen_to_world(canvas_w / 2.0, canvas_h / 2.0)

        # Avoid the top-left legend region (in screen coordinates) when placing nodes
        def in_legend_zone(wx, wy):
            sx, sy = self.world_to_screen(wx, wy)
            return sx < 220 and sy < 200

        if not self._overlaps_existing(cx, cy, est_w, est_h) and not in_legend_zone(cx, cy):
            return cx, cy

        # Search outward in concentric rings in world coordinates
        for ring in range(1, 20):
            radius_x = ring * 155
            radius_y = ring * 95
            steps = max(12, ring * 10)
            for step in range(steps):
                angle = (2 * math.pi * step) / steps
                cand_x = cx + math.cos(angle) * radius_x
                cand_y = cy + math.sin(angle) * radius_y
                if not (min_x <= cand_x <= max_x and min_y <= cand_y <= max_y):
                    continue
                if in_legend_zone(cand_x, cand_y):
                    continue
                if not self._overlaps_existing(cand_x, cand_y, est_w, est_h):
                    return cand_x, cand_y

        # Grid scan across visible world area
        col_step = max(140, int(est_w + 26))
        row_step = 76
        gx = min_x
        while gx <= max_x:
            gy = min_y
            while gy <= max_y:
                if not in_legend_zone(gx, gy) and not self._overlaps_existing(gx, gy, est_w, est_h):
                    return float(gx), float(gy)
                gy += row_step
            gx += col_step

        # Unbounded ring fallback if visible viewport is completely full
        for ring in range(1, 30):
            radius_x = ring * 165
            radius_y = ring * 105
            steps = 16 + ring * 6
            for step in range(steps):
                angle = (2 * math.pi * step) / steps
                cand_x = cx + math.cos(angle) * radius_x
                cand_y = cy + math.sin(angle) * radius_y
                if not self._overlaps_existing(cand_x, cand_y, est_w, est_h):
                    return cand_x, cand_y

        offset = (len(self.nodes) % 10) * 30
        return cx + offset, cy + offset

    def _create_node(self, name, near_node=None):
        x, y = self._find_empty_position(name, near_node=near_node)
        node = {
            "name": name,
            "x": x,
            "y": y,
            "tag": f"node_{self.next_id}",
        }
        self.next_id += 1
        self.nodes.append(node)
        return node

    def _ensure_node(self, name, near_node=None):
        existing = self._find_node_by_name(name)
        if existing is not None:
            return existing
        return self._create_node(name, near_node=near_node)

    def _sync_type_row(self):
        """Show the Type dropdown under the selected item's name (hidden in route mode)."""
        if self.route_start is not None or self.selected_node is None:
            if self.type_row.winfo_ismapped():
                self.type_row.pack_forget()
            return
        self.type_var.set("Liquid" if is_liquid(self.selected_node) else "Item")
        if not self.type_row.winfo_ismapped():
            self.type_row.pack(side=tk.TOP, fill=tk.X, before=self.actions_bar)

    def on_item_type_change(self, _choice):
        if self.selected_node is None or self.route_start is not None:
            return
        new_type = normalize_node_type(self.type_var.get())
        if new_type == "liquid":
            self.selected_node["type"] = "liquid"
        else:
            self.selected_node.pop("type", None)
        self._save_state()
        # Outline colour depends on the type, so redraw the node visuals
        update_node_selection_visuals(
            self.canvas, self.nodes, self.selected_node, zoom=self.zoom, **self._node_visual_kwargs()
        )
        self._redraw_lines()
        self.refresh_side_panel_paths()

    def select_node(self, node):
        if node is None:
            self.close_side_panel()
            return

        node_changed = node is not self.selected_node
        self.selected_node = node
        update_node_selection_visuals(
            self.canvas, self.nodes, self.selected_node, zoom=self.zoom, **self._node_visual_kwargs()
        )
        self._redraw_lines()

        if not self.side_panel.winfo_ismapped():
            self.side_panel.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)

        self.panel_title_label.configure(text=node["name"])
        self._sync_type_row()
        if node_changed and self.form_visible:
            self.hide_add_path_form()
        self.refresh_side_panel_paths()

    def close_side_panel(self):
        self.selected_node = None
        update_node_selection_visuals(
            self.canvas, self.nodes, None, zoom=self.zoom, **self._node_visual_kwargs()
        )
        self._redraw_lines()
        self.hide_add_path_form()
        self._sync_type_row()
        if self.side_panel.winfo_ismapped():
            self.side_panel.pack_forget()

    def open_add_path_form(self):
        if self.selected_node is None:
            return
        # "Add path" always creates a new path; editing goes through edit_path()
        self.editing_path = None
        self.save_path_btn.configure(text="Save path")
        if not self.form_visible:
            self.form_frame.pack(
                side=tk.TOP,
                fill=tk.X,
                padx=14,
                pady=(0, 10),
                before=self.paths_container,
            )
            self.form_visible = True

        self.method_entry.delete(0, tk.END)
        self.inputs_entry.delete(0, tk.END)
        self.inputs_entry.insert(0, self.selected_node["name"])
        self.outputs_entry.delete(0, tk.END)
        self._reset_form_hints()
        self.method_entry.focus_set()

    def edit_path(self, path_obj):
        """Open the path form pre-filled with this path, so clicking a path card in
        the side panel lets you change its method/inputs/outputs in place."""
        if not self.side_panel.winfo_ismapped():
            return
        self.editing_path = path_obj
        self.save_path_btn.configure(text="Save changes")
        if not self.form_visible:
            self.form_frame.pack(
                side=tk.TOP,
                fill=tk.X,
                padx=14,
                pady=(0, 10),
                before=self.paths_container,
            )
            self.form_visible = True

        self.method_entry.delete(0, tk.END)
        self.method_entry.insert(0, path_obj["method"])
        self.inputs_entry.delete(0, tk.END)
        self.inputs_entry.insert(
            0, ", ".join(format_input_entry(path_obj, i) for i in path_obj["inputs"])
        )
        self.outputs_entry.delete(0, tk.END)
        self.outputs_entry.insert(
            0, ", ".join(format_output_entry(path_obj, o) for o in path_obj["outputs"])
        )
        self._reset_form_hints()
        self.method_entry.focus_set()

    def hide_add_path_form(self):
        self.editing_path = None
        if self.form_visible:
            self.form_frame.pack_forget()
            self.form_visible = False

    def _reset_form_hints(self):
        self.inputs_hint.configure(text=self.inputs_hint_text, fg=MUTED_FG)
        self.outputs_hint.configure(text=self.outputs_hint_text, fg=MUTED_FG)

    def _flag_hint(self, which, message):
        # Show the problem inline under the offending box (plus the popup below)
        hint = self.inputs_hint if which == "inputs" else self.outputs_hint
        hint.configure(text=str(message), fg=DANGER_BTN_BG)

    def submit_add_path_form(self):
        raw_method = self.method_entry.get().strip()
        self._reset_form_hints()
        try:
            parsed_inputs = parse_inputs_with_amounts(self.inputs_entry.get())
        except AmountError as exc:
            self._flag_hint("inputs", exc)
            messagebox.showwarning("Invalid amount", str(exc), parent=self.root)
            return
        try:
            parsed_outputs = parse_outputs_with_amounts_chances(self.outputs_entry.get())
        except AmountError as exc:
            self._flag_hint("outputs", exc)
            messagebox.showwarning("Invalid amount", str(exc), parent=self.root)
            return
        except ValueError as exc:
            self._flag_hint("outputs", exc)
            messagebox.showwarning("Invalid percentage", str(exc), parent=self.root)
            return
        raw_inputs = [name for name, _amount in parsed_inputs]
        raw_outputs = [name for name, _amount, _chance in parsed_outputs]

        if not raw_method:
            messagebox.showwarning("Missing Method", "Please enter a method name.", parent=self.root)
            return
        if not raw_inputs:
            messagebox.showwarning("Missing Inputs", "Please enter at least one input item.", parent=self.root)
            return
        if not raw_outputs:
            messagebox.showwarning("Missing Outputs", "Please enter at least one output item.", parent=self.root)
            return

        # Reuse canonical method display name if this method already exists (ignore capitalization)
        canonical_method = self._canonical_method_name(raw_method)
        self._ensure_method_color(canonical_method)

        anchor_node = self.selected_node
        canonical_inputs = []
        input_amounts = {}
        for item_name, amount in parsed_inputs:
            node = self._ensure_node(item_name, near_node=anchor_node)
            canonical_inputs.append(node["name"])
            input_amounts[node["name"].strip().lower()] = int(amount)

        first_input_node = self._find_node_by_name(canonical_inputs[0]) or anchor_node
        canonical_outputs = []
        chances = {}
        output_amounts = {}
        for item_name, amount, chance in parsed_outputs:
            node = self._ensure_node(item_name, near_node=first_input_node)
            canonical_outputs.append(node["name"])
            output_amounts[node["name"].strip().lower()] = int(amount)
            if chance is not None:
                chances[node["name"].strip().lower()] = float(chance)

        amounts = {"inputs": input_amounts, "outputs": output_amounts}
        amounts = normalize_amounts(amounts)

        editing = self.editing_path
        is_editing = editing is not None and any(p is editing for p in self.paths)
        if is_editing:
            # Update the existing path in place instead of adding a duplicate
            editing["method"] = canonical_method
            editing["inputs"] = canonical_inputs
            editing["outputs"] = canonical_outputs
            # Arrowhead settings are kept for input/output pairs that still exist and
            # dropped for pairs that no longer exist
            prune_path_arrows(editing)
            # Chances follow the outputs (each output has its own independent chance)
            if chances:
                editing["chances"] = chances
            else:
                editing.pop("chances", None)
            # Amounts follow the items (kept for items still in the path)
            if amounts:
                editing["amounts"] = amounts
            else:
                editing.pop("amounts", None)
        else:
            new_path = {
                "method": canonical_method,
                "inputs": canonical_inputs,
                "outputs": canonical_outputs,
            }
            if chances:
                new_path["chances"] = chances
            if amounts:
                new_path["amounts"] = amounts
            self.paths.append(new_path)
        self.editing_path = None

        self._save_state()
        # Full redraw recalculates node sizes from the new path right away
        self._redraw_scene()
        self.refresh_legend()
        self.hide_add_path_form()
        self.refresh_side_panel_paths()
        self._refresh_routes_after_edit()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()

    def delete_path(self, path_obj):
        if self.editing_path is path_obj:
            self.editing_path = None
            self.hide_add_path_form()
        self.paths = [p for p in self.paths if p is not path_obj]
        self._save_state()
        # Full redraw recalculates node sizes after the path is gone
        self._redraw_scene()
        self.refresh_legend()
        self.refresh_side_panel_paths()
        self._refresh_routes_after_edit()

    def refresh_side_panel_paths(self):
        if self.route_start is not None:
            # While a route selection is active the side panel lists the routes
            self._render_route_panel()
            return

        self._clear_path_list_children()

        self._sync_type_row()
        if self.selected_node is None:
            self._sync_paths_scrollregion()
            return

        item_name = self.selected_node["name"]
        node_by_key = {n["name"].strip().lower(): n for n in self.nodes}
        matching_paths = [p for p in self.paths if path_involves_item(p, item_name)]

        if not matching_paths:
            empty_label = tk.Label(
                self.paths_list_frame,
                text="No paths involving this item yet.",
                bg=PANEL_BG,
                fg=MUTED_FG,
                font=("Segoe UI", 10),
                anchor="w",
                justify=tk.LEFT,
            )
            empty_label.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
            self._render_item_sections(item_name)
            self._sync_paths_scrollregion()
            return

        for path_obj in matching_paths:
            card = tk.Frame(
                self.paths_list_frame,
                bg=CARD_BG,
                padx=10,
                pady=8,
                highlightbackground=PANEL_BORDER,
                highlightthickness=1,
            )
            card.pack(side=tk.TOP, fill=tk.X, pady=(0, 8))

            edit_btn = tk.Button(
                card,
                text="Edit",
                command=lambda p=path_obj: self.edit_path(p),
                bg=SECONDARY_BTN_BG,
                fg=INPUT_FG,
                activebackground=SECONDARY_BTN_ACTIVE_BG,
                activeforeground=BTN_FG,
                relief=tk.FLAT,
                bd=0,
                padx=8,
                pady=3,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            edit_btn.pack(side=tk.RIGHT)

            del_btn = tk.Button(
                card,
                text="Delete",
                command=lambda p=path_obj: self.delete_path(p),
                bg=DANGER_BTN_BG,
                fg=BTN_FG,
                activebackground=DANGER_BTN_ACTIVE_BG,
                activeforeground=BTN_FG,
                relief=tk.FLAT,
                bd=0,
                padx=8,
                pady=3,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )
            del_btn.pack(side=tk.RIGHT, padx=(8, 0))

            m_color = self.method_colors.get(path_obj["method"].strip().lower(), BTN_BG)
            dot = tk.Canvas(
                card,
                width=10,
                height=10,
                bg=m_color,
                highlightthickness=0,
            )
            dot.pack(side=tk.LEFT, padx=(0, 8))

            text_label = tk.Label(
                card,
                text=format_path(path_obj, node_by_key),
                bg=CARD_BG,
                fg=NODE_TEXT,
                font=("Segoe UI", 10),
                anchor="w",
                justify=tk.LEFT,
                wraplength=PANEL_WIDTH - 150,
            )
            text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Clicking the path card (anything but its Delete button) opens it for editing
            for clickable in (card, dot, text_label):
                clickable.bind("<Button-1>", lambda _e, p=path_obj: self.edit_path(p))
                clickable.configure(cursor="hand2")

        self._render_item_sections(item_name)
        self.paths_canvas.yview_moveto(0)
        self._sync_paths_scrollregion()

    def add_item(self):
        name = self.entry.get().strip()
        if not name:
            return

        if self._find_node_by_name(name) is not None:
            messagebox.showwarning(
                "Duplicate Item",
                f'"{name}" already exists.',
                parent=self.root,
            )
            return

        self._create_node(name)
        self._redraw_scene()
        self._save_state()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()

        self.entry.delete(0, tk.END)
        self.entry.focus_set()

    def on_left_press(self, event):
        self.context_menu.unpost()

        if event.state & SHIFT_MASK:
            # Shift+click marks route endpoints only: it never drags the node
            # and never opens the node's normal side panel
            self.drag_state = {
                "mode": None,
                "node": None,
                "start_x": 0,
                "start_y": 0,
                "last_x": 0,
                "last_y": 0,
                "dragging": False,
            }
            node = self._find_node_at(event.x, event.y)
            if node is not None:
                self._on_shift_click_node(node)
            return

        if self.route_start is not None:
            # Any plain click (including on empty space) clears the route selection
            self.clear_route_selection()

        # Clicking near a line end toggles the arrowhead on that end; clicking
        # anywhere else on a line or on a node behaves exactly as before
        end_hit = self._find_edge_end_at(event.x, event.y)
        if end_hit is not None:
            edge, which = end_hit
            self.drag_state = {
                "mode": None,
                "node": None,
                "start_x": 0,
                "start_y": 0,
                "last_x": 0,
                "last_y": 0,
                "dragging": False,
            }
            self._toggle_edge_end(edge, which)
            return

        node = self._find_node_at(event.x, event.y)
        if node is None:
            self.drag_state = {
                "mode": "pan",
                "node": None,
                "start_x": event.x,
                "start_y": event.y,
                "last_x": event.x,
                "last_y": event.y,
                "dragging": False,
            }
            return

        self.canvas.tag_raise(node["tag"])
        self.drag_state = {
            "mode": "node",
            "node": node,
            "start_x": event.x,
            "start_y": event.y,
            "last_x": event.x,
            "last_y": event.y,
            "dragging": False,
        }

    def on_left_drag(self, event):
        mode = self.drag_state["mode"]
        if mode is None:
            return

        if not self.drag_state["dragging"]:
            dist_sq = (event.x - self.drag_state["start_x"]) ** 2 + (
                event.y - self.drag_state["start_y"]
            ) ** 2
            if dist_sq < CLICK_DRAG_THRESHOLD ** 2:
                return
            self.drag_state["dragging"] = True
            self.drag_state["last_x"] = self.drag_state["start_x"]
            self.drag_state["last_y"] = self.drag_state["start_y"]

        dx = event.x - self.drag_state["last_x"]
        dy = event.y - self.drag_state["last_y"]
        if dx == 0 and dy == 0:
            return

        self.drag_state["last_x"] = event.x
        self.drag_state["last_y"] = event.y

        if mode == "node":
            node = self.drag_state["node"]
            if node is None:
                return
            # Store unzoomed world coordinates so zoom never alters saved layout
            node["x"] += dx / self.zoom
            node["y"] += dy / self.zoom
            self._schedule_redraw()
        elif mode == "pan":
            # The canvas is infinite: panning just moves the viewport and the
            # redraw draws whatever has come into view (and drops what left)
            self.pan_x += dx
            self.pan_y += dy
            self._schedule_redraw()

    def on_left_release(self, _event):
        mode = self.drag_state["mode"]
        node = self.drag_state["node"]
        was_dragging = self.drag_state["dragging"]
        self.drag_state = {
            "mode": None,
            "node": None,
            "start_x": 0,
            "start_y": 0,
            "last_x": 0,
            "last_y": 0,
            "dragging": False,
        }

        if mode == "node" and node is not None:
            if was_dragging:
                self._save_state()
            else:
                self.select_node(node)
        elif mode == "pan" and not was_dragging:
            if self.selected_node is not None:
                self.close_side_panel()

    def on_right_click(self, event):
        node = self._find_node_at(event.x, event.y)
        if node is None:
            return

        self.context_node = node
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def delete_context_node(self):
        if self.context_node is None:
            return

        node = self.context_node
        self.context_node = None

        if node is self.route_start or node is self.route_end:
            self.clear_route_selection(redraw=False)

        item_name = node["name"]
        item_key = item_name.strip().lower()
        related_paths = [p for p in self.paths if path_involves_item(p, item_name)]
        count = len(related_paths)

        # Only show confirmation when the node has one or more paths
        if count > 0:
            # Deleting an item only removes it from its paths; a path is
            # deleted only when no inputs or no outputs would remain
            def would_be_empty(p):
                ins = [n for n in p["inputs"] if n.strip().lower() != item_key]
                outs = [n for n in p["outputs"] if n.strip().lower() != item_key]
                return not ins or not outs

            dying = sum(1 for p in related_paths if would_be_empty(p))
            if dying == count:
                if count == 1:
                    prompt = f'Delete "{item_name}"?\n\nThis will also delete 1 path that uses this item.'
                else:
                    prompt = f'Delete "{item_name}"?\n\nThis will also delete {count} paths that use this item.'
            elif dying:
                prompt = (
                    f'Delete "{item_name}"?\n\nThis will remove it from {count - dying} path(s) '
                    f'and delete {dying} path(s) that would be left empty.'
                )
            else:
                prompt = (
                    f'Delete "{item_name}"?\n\nThis will remove it from {count} path(s); '
                    f'no paths are deleted.'
                )

            confirmed = messagebox.askyesno(
                "Confirm Delete",
                prompt,
                parent=self.root,
            )
            if not confirmed:
                return

            # Surgically remove the item from each related path instead of deleting
            # whole paths, so other items sharing a path keep their lines
            related_ids = {id(p) for p in related_paths}
            new_paths = []
            for p in self.paths:
                if id(p) in related_ids:
                    p["inputs"] = [n for n in p["inputs"] if n.strip().lower() != item_key]
                    p["outputs"] = [n for n in p["outputs"] if n.strip().lower() != item_key]
                    prune_path_arrows(p)
                    prune_path_chances(p)
                    prune_path_amounts(p)
                    if not (p["inputs"] and p["outputs"]):
                        continue  # path would have no inputs/outputs left: delete it
                new_paths.append(p)
            self.paths = new_paths

        if node is self.selected_node:
            self.close_side_panel()
        elif self.selected_node is not None:
            self.refresh_side_panel_paths()

        self.nodes = [n for n in self.nodes if n is not node]
        # Redraw removes the node's items and resizes the remaining nodes
        # (their paths were deleted above, so their sizes shrink immediately)
        self._redraw_scene()
        self.refresh_legend()
        self._save_state()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()

    def change_context_node_color(self):
        node = self.context_node
        if node is None:
            return
        chosen = colorchooser.askcolor(
            color=node_fill_color(node),
            title=f"Choose colour for {node['name']}",
            parent=self.root,
        )
        if chosen and chosen[1]:
            hex_color = _normalize_hex_color(chosen[1])
            if hex_color:
                node["color"] = hex_color
                self._save_state()
                # Apply immediately (respects the current dim/highlight state)
                update_node_selection_visuals(
                    self.canvas, self.nodes, self.selected_node, zoom=self.zoom,
                    **self._node_visual_kwargs(),
                )

    def reset_context_node_color(self):
        node = self.context_node
        if node is None:
            return
        if node.get("color") is not None:
            node.pop("color", None)
            self._save_state()
            update_node_selection_visuals(
                self.canvas, self.nodes, self.selected_node, zoom=self.zoom,
                **self._node_visual_kwargs(),
            )

    # --- Renaming an item after it was created ---

    def rename_context_node(self):
        self.rename_item(self.context_node)

    def rename_selected_node(self):
        self.rename_item(self.selected_node)

    def rename_item(self, node):
        """Rename an item in place: the node plus every path reference
        (inputs/outputs, arrowhead pair keys, chance keys), then redraw + save."""
        if node is None:
            return
        old_name = node["name"]
        new_name = simpledialog.askstring(
            "Rename item",
            f'New name for "{old_name}":',
            initialvalue=old_name,
            parent=self.root,
        )
        if new_name is None:
            return  # cancelled
        new_name = new_name.strip()
        if not new_name:
            messagebox.showwarning("Invalid name", "The name cannot be empty.", parent=self.root)
            return
        if new_name == old_name:
            return
        existing = self._find_node_by_name(new_name)
        if existing is not None and existing is not node:
            messagebox.showwarning(
                "Duplicate Item",
                f'"{new_name}" already exists.',
                parent=self.root,
            )
            return
        rename_item_everywhere(self.nodes, self.paths, old_name, new_name)
        self._save_state()
        self._redraw_scene()
        self.refresh_legend()
        if self.selected_node is node:
            self.panel_title_label.configure(text=new_name)
            self.refresh_side_panel_paths()
        self._refresh_routes_after_edit()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()
        self.show_status(f'Renamed "{old_name}" to "{new_name}"', auto_hide_ms=4000)


def main():
    root = tk.Tk()
    CreateItemTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
