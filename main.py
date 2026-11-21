import json
import math
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, messagebox


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
NODE_TEXT = "#f0f6fc"
NODE_RADIUS = 12
NODE_PAD_X = 18
NODE_PAD_Y = 12
NODE_MIN_W = 110
NODE_MIN_H = 44

LINE_WIDTH_NORMAL = 2.2
LINE_WIDTH_SELECTED = 4.0
LINE_WIDTH_DIMMED = 1.6
DIM_BLEND_FACTOR = 0.25  # 25% method colour + 75% canvas background

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


def format_path(path):
    method = path["method"]
    inputs_str = ", ".join(path["inputs"])
    outputs_str = ", ".join(path["outputs"])
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
                nodes.append({"name": name, "x": x, "y": y})

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
                paths.append(
                    {
                        "method": method,
                        "inputs": inputs,
                        "outputs": outputs,
                    }
                )

        return nodes, paths, method_colors
    except (OSError, json.JSONDecodeError):
        return [], [], {}


def save_data(nodes, paths, method_colors):
    payload = {
        "nodes": [
            {"name": node["name"], "x": round(node["x"], 2), "y": round(node["y"], 2)}
            for node in nodes
        ],
        "paths": [
            {
                "method": path["method"],
                "inputs": list(path["inputs"]),
                "outputs": list(path["outputs"]),
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


def measure_node_base_size(canvas, node):
    if "base_width" in node and "base_height" in node:
        return node["base_width"], node["base_height"]

    probe_id = canvas.create_text(
        0,
        0,
        text=node["name"],
        font=("Segoe UI", 11, "bold"),
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


def draw_node(canvas, node, tag, selected=False, zoom=1.0, pan_x=0.0, pan_y=0.0):
    base_w, base_h = measure_node_base_size(canvas, node)

    sx = node["x"] * zoom + pan_x
    sy = node["y"] * zoom + pan_y
    width = base_w * zoom
    height = base_h * zoom
    radius = NODE_RADIUS * zoom

    font_size = max(4, int(round(11 * zoom)))
    outline_w = max(1.0, (2.5 if selected else 2.0) * zoom)
    outline_color = NODE_SELECTED_OUTLINE if selected else NODE_OUTLINE

    x1, y1 = sx - width / 2.0, sy - height / 2.0
    x2, y2 = sx + width / 2.0, sy + height / 2.0

    points = rounded_rect_points(x1, y1, x2, y2, radius)
    rect_id = canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=24,
        fill=NODE_FILL,
        outline=outline_color,
        width=outline_w,
        tags=(tag, "node"),
    )
    text_id = canvas.create_text(
        sx,
        sy,
        text=node["name"],
        fill=NODE_TEXT,
        font=("Segoe UI", font_size, "bold"),
        tags=(tag, "node"),
    )
    canvas.tag_raise(text_id, rect_id)

    node["tag"] = tag
    node["rect_id"] = rect_id
    node["text_id"] = text_id
    node["width"] = base_w
    node["height"] = base_h


def draw_connections(
    canvas,
    nodes,
    paths,
    method_colors,
    selected_node=None,
    zoom=1.0,
    pan_x=0.0,
    pan_y=0.0,
):
    canvas.delete("connection")
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

                edge = {
                    "src": src,
                    "dst": dst,
                    "src_key": src_key,
                    "dst_key": dst_key,
                    "color": base_color,
                    "connected": connected_to_selected,
                }
                raw_edges.append(edge)
                pair_key = tuple(sorted((src_key, dst_key)))
                pair_buckets.setdefault(pair_key, []).append(edge)

    for bucket in pair_buckets.values():
        count = len(bucket)
        for idx, edge in enumerate(bucket):
            edge["offset_index"] = idx - (count - 1) / 2.0

    # Draw dimmed/unselected lines first so highlighted lines sit cleanly on top of other lines
    ordered_edges = sorted(raw_edges, key=lambda e: 1 if e["connected"] else 0)

    for edge in ordered_edges:
        src = edge["src"]
        dst = edge["dst"]

        if selected_key is None:
            line_color = edge["color"]
            base_lw = LINE_WIDTH_NORMAL
            base_arrow = (11, 13, 5)
        elif edge["connected"]:
            line_color = edge["color"]
            base_lw = LINE_WIDTH_SELECTED
            base_arrow = (13, 16, 6)
        else:
            line_color = blend_colors(edge["color"], BG_COLOR, DIM_BLEND_FACTOR)
            base_lw = LINE_WIDTH_DIMMED
            base_arrow = (9, 11, 4)

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

        sw = (src.get("base_width", src.get("width", NODE_MIN_W)) * zoom) / 2.0
        sh = (src.get("base_height", src.get("height", NODE_MIN_H)) * zoom) / 2.0
        dw = (dst.get("base_width", dst.get("width", NODE_MIN_W)) * zoom) / 2.0
        dh = (dst.get("base_height", dst.get("height", NODE_MIN_H)) * zoom) / 2.0

        # Self-loop fallback if an item is both input and output of the same path
        if src is dst:
            loop_r = (28 + abs(edge["offset_index"]) * 10) * zoom
            sx = x1 + sw * 0.5
            sy = y1 - sh
            ex = x1 - sw * 0.5
            ey = y1 - sh
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
                arrow=tk.LAST,
                arrowshape=arrow_shape,
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
            canvas.create_line(
                sx,
                sy,
                ex,
                ey,
                fill=line_color,
                width=line_width,
                arrow=tk.LAST,
                arrowshape=arrow_shape,
                capstyle=tk.ROUND,
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
                arrow=tk.LAST,
                arrowshape=arrow_shape,
                capstyle=tk.ROUND,
                tags=("connection",),
            )

    if canvas.find_withtag("node"):
        canvas.tag_lower("connection", "node")


def update_node_selection_visuals(canvas, nodes, selected_node, zoom=1.0):
    for node in nodes:
        rect_id = node.get("rect_id")
        if rect_id:
            is_selected = node is selected_node
            outline_w = max(1.0, (2.5 if is_selected else 2.0) * zoom)
            canvas.itemconfigure(
                rect_id,
                outline=NODE_SELECTED_OUTLINE if is_selected else NODE_OUTLINE,
                width=outline_w,
            )


def redraw_all(
    canvas,
    nodes,
    paths=None,
    method_colors=None,
    selected_node=None,
    zoom=1.0,
    pan_x=0.0,
    pan_y=0.0,
):
    canvas.delete("node")
    for idx, node in enumerate(nodes):
        tag = node.get("tag") or f"node_{idx + 1}"
        draw_node(
            canvas,
            node,
            tag,
            selected=(node is selected_node),
            zoom=zoom,
            pan_x=pan_x,
            pan_y=pan_y,
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
        self.search_matches = []

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
        self.context_menu.add_command(label="Delete", command=self.delete_context_node)

        self.canvas.bind("<ButtonPress-1>", self.on_left_press)
        self.canvas.bind("<B1-Motion>", self.on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_left_release)

        # Mouse wheel zoom (Windows/macOS <MouseWheel>, Linux X11 <Button-4>/<Button-5>)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel_up)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel_down)

        # Support right-click across Windows/Linux (<Button-3>) and macOS (<Button-2> / Ctrl-Click)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click)
        self.canvas.bind("<ButtonPress-2>", self.on_right_click)
        self.canvas.bind("<Control-Button-1>", self.on_right_click)

        # Dismiss search dropdown when clicking outside search widgets
        self.root.bind("<ButtonPress-1>", self._on_global_click, add="+")
        self.root.bind("<Configure>", lambda _e: self._reposition_search_dropdown(), add="+")

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

        divider = tk.Frame(self.side_panel, bg=PANEL_BORDER, height=1)
        divider.pack(side=tk.TOP, fill=tk.X)

        actions_bar = tk.Frame(self.side_panel, bg=PANEL_BG, padx=14, pady=10)
        actions_bar.pack(side=tk.TOP, fill=tk.X)

        paths_heading = tk.Label(
            actions_bar,
            text="Paths",
            bg=PANEL_BG,
            fg=MUTED_FG,
            font=("Segoe UI", 10, "bold"),
        )
        paths_heading.pack(side=tk.LEFT)

        self.add_path_btn = tk.Button(
            actions_bar,
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
        self.inputs_entry.pack(side=tk.TOP, fill=tk.X, ipady=4, pady=(2, 8))

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
        self.outputs_entry.pack(side=tk.TOP, fill=tk.X, ipady=4, pady=(2, 10))
        self.method_entry.bind("<Return>", lambda _event: self.inputs_entry.focus_set())
        self.inputs_entry.bind("<Return>", lambda _event: self.outputs_entry.focus_set())
        self.outputs_entry.bind("<Return>", lambda _event: self.submit_add_path_form())

        form_btns = tk.Frame(self.form_frame, bg=CARD_BG)
        form_btns.pack(side=tk.TOP, fill=tk.X)

        save_path_btn = tk.Button(
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
        save_path_btn.pack(side=tk.LEFT)

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

    def _redraw_scene(self):
        redraw_all(
            self.canvas,
            self.nodes,
            self.paths,
            self.method_colors,
            selected_node=self.selected_node,
            zoom=self.zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
        )

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
        )

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

    # --- Persistence & state ---

    def _load_initial_state(self):
        loaded_nodes, loaded_paths, loaded_colors = load_data()
        self.paths = loaded_paths
        self.method_colors = loaded_colors

        for entry in loaded_nodes:
            node = {
                "name": entry["name"],
                "x": entry["x"],
                "y": entry["y"],
            }
            tag = f"node_{self.next_id}"
            self.next_id += 1
            draw_node(
                self.canvas,
                node,
                tag,
                selected=False,
                zoom=self.zoom,
                pan_x=self.pan_x,
                pan_y=self.pan_y,
            )
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

        self._redraw_lines()
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
            nw = node.get("base_width", node.get("width", NODE_MIN_W)) / 2.0
            nh = node.get("base_height", node.get("height", NODE_MIN_H)) / 2.0
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
        node = {"name": name, "x": x, "y": y}
        tag = f"node_{self.next_id}"
        self.next_id += 1
        draw_node(
            self.canvas,
            node,
            tag,
            selected=False,
            zoom=self.zoom,
            pan_x=self.pan_x,
            pan_y=self.pan_y,
        )
        self.nodes.append(node)
        return node

    def _ensure_node(self, name, near_node=None):
        existing = self._find_node_by_name(name)
        if existing is not None:
            return existing
        return self._create_node(name, near_node=near_node)

    def select_node(self, node):
        if node is None:
            self.close_side_panel()
            return

        node_changed = node is not self.selected_node
        self.selected_node = node
        update_node_selection_visuals(self.canvas, self.nodes, self.selected_node, zoom=self.zoom)
        self._redraw_lines()

        if not self.side_panel.winfo_ismapped():
            self.side_panel.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)

        self.panel_title_label.configure(text=node["name"])
        if node_changed and self.form_visible:
            self.hide_add_path_form()
        self.refresh_side_panel_paths()

    def close_side_panel(self):
        self.selected_node = None
        update_node_selection_visuals(self.canvas, self.nodes, None, zoom=self.zoom)
        self._redraw_lines()
        self.hide_add_path_form()
        if self.side_panel.winfo_ismapped():
            self.side_panel.pack_forget()

    def open_add_path_form(self):
        if self.selected_node is None:
            return
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
        self.method_entry.focus_set()

    def hide_add_path_form(self):
        if self.form_visible:
            self.form_frame.pack_forget()
            self.form_visible = False

    def submit_add_path_form(self):
        raw_method = self.method_entry.get().strip()
        raw_inputs = parse_comma_separated(self.inputs_entry.get())
        raw_outputs = parse_comma_separated(self.outputs_entry.get())

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
        for item_name in raw_inputs:
            node = self._ensure_node(item_name, near_node=anchor_node)
            canonical_inputs.append(node["name"])

        first_input_node = self._find_node_by_name(canonical_inputs[0]) or anchor_node
        canonical_outputs = []
        for item_name in raw_outputs:
            node = self._ensure_node(item_name, near_node=first_input_node)
            canonical_outputs.append(node["name"])

        self.paths.append(
            {
                "method": canonical_method,
                "inputs": canonical_inputs,
                "outputs": canonical_outputs,
            }
        )

        self._save_state()
        self._redraw_lines()
        self.refresh_legend()
        self.hide_add_path_form()
        self.refresh_side_panel_paths()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()

    def delete_path(self, path_obj):
        self.paths = [p for p in self.paths if p is not path_obj]
        self._save_state()
        self._redraw_lines()
        self.refresh_legend()
        self.refresh_side_panel_paths()

    def refresh_side_panel_paths(self):
        for child in self.paths_list_frame.winfo_children():
            child.destroy()

        if self.selected_node is None:
            self._sync_paths_scrollregion()
            return

        item_name = self.selected_node["name"]
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
                text=format_path(path_obj),
                bg=CARD_BG,
                fg=NODE_TEXT,
                font=("Segoe UI", 10),
                anchor="w",
                justify=tk.LEFT,
                wraplength=PANEL_WIDTH - 150,
            )
            text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

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
        self._redraw_lines()
        self._save_state()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()

        self.entry.delete(0, tk.END)
        self.entry.focus_set()

    def on_left_press(self, event):
        self.context_menu.unpost()
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
            self.canvas.move(node["tag"], dx, dy)
            # Store unzoomed world coordinates so zoom never alters saved layout
            node["x"] += dx / self.zoom
            node["y"] += dy / self.zoom
            self._redraw_lines()
        elif mode == "pan":
            self.pan_x += dx
            self.pan_y += dy
            self.canvas.move("node", dx, dy)
            self.canvas.move("connection", dx, dy)

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

        item_name = node["name"]
        related_paths = [p for p in self.paths if path_involves_item(p, item_name)]
        count = len(related_paths)

        # Only show confirmation when the node has one or more paths
        if count > 0:
            if count == 1:
                prompt = f'Delete "{item_name}"?\n\nThis will also delete 1 path that uses this item.'
            else:
                prompt = f'Delete "{item_name}"?\n\nThis will also delete {count} paths that use this item.'

            confirmed = messagebox.askyesno(
                "Confirm Delete",
                prompt,
                parent=self.root,
            )
            if not confirmed:
                return

            related_ids = {id(p) for p in related_paths}
            self.paths = [p for p in self.paths if id(p) not in related_ids]

        if node is self.selected_node:
            self.close_side_panel()
        elif self.selected_node is not None:
            self.refresh_side_panel_paths()

        self.canvas.delete(node["tag"])
        self.nodes = [n for n in self.nodes if n is not node]
        self._redraw_lines()
        self.refresh_legend()
        self._save_state()
        if self.search_dropdown.winfo_ismapped():
            self.update_search_dropdown()


def main():
    root = tk.Tk()
    CreateItemTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
