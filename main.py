import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


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

PANEL_WIDTH = 360
CLICK_DRAG_THRESHOLD = 5


def _parse_item_list(raw_items):
    if not isinstance(raw_items, list):
        return []
    cleaned = []
    for item in raw_items:
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def parse_comma_separated(text):
    return [part.strip() for part in text.split(",") if part.strip()]


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


def load_data():
    if not DATA_FILE.exists():
        return [], []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        # Support both legacy list format and new {"nodes": [...], "paths": [...]} format
        if isinstance(raw, list):
            raw_nodes = raw
            raw_paths = []
        elif isinstance(raw, dict):
            raw_nodes = raw.get("nodes", [])
            raw_paths = raw.get("paths", [])
        else:
            return [], []

        nodes = []
        seen = set()
        if isinstance(raw_nodes, list):
            for entry in raw_nodes:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                if not name or name.lower() in seen:
                    continue
                try:
                    x = float(entry.get("x", 100))
                    y = float(entry.get("y", 100))
                except (TypeError, ValueError):
                    x, y = 100.0, 100.0
                seen.add(name.lower())
                nodes.append({"name": name, "x": x, "y": y})

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
                paths.append(
                    {
                        "method": method,
                        "inputs": inputs,
                        "outputs": outputs,
                    }
                )

        return nodes, paths
    except (OSError, json.JSONDecodeError):
        return [], []


def save_data(nodes, paths):
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


def draw_node(canvas, node, tag, selected=False):
    x, y = node["x"], node["y"]
    text_id = canvas.create_text(
        x,
        y,
        text=node["name"],
        fill=NODE_TEXT,
        font=("Segoe UI", 11, "bold"),
        tags=(tag, "node"),
    )
    bbox = canvas.bbox(text_id)
    if bbox:
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    else:
        text_w = len(node["name"]) * 8
        text_h = 18

    width = max(NODE_MIN_W, text_w + NODE_PAD_X * 2)
    height = max(NODE_MIN_H, text_h + NODE_PAD_Y * 2)
    x1, y1 = x - width / 2, y - height / 2
    x2, y2 = x + width / 2, y + height / 2

    outline_color = NODE_SELECTED_OUTLINE if selected else NODE_OUTLINE
    points = rounded_rect_points(x1, y1, x2, y2, NODE_RADIUS)
    rect_id = canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=24,
        fill=NODE_FILL,
        outline=outline_color,
        width=2,
        tags=(tag, "node"),
    )
    canvas.tag_raise(text_id, rect_id)

    node["tag"] = tag
    node["rect_id"] = rect_id
    node["text_id"] = text_id


def update_node_selection_visuals(canvas, nodes, selected_node):
    for node in nodes:
        rect_id = node.get("rect_id")
        if rect_id:
            is_selected = node is selected_node
            canvas.itemconfigure(
                rect_id,
                outline=NODE_SELECTED_OUTLINE if is_selected else NODE_OUTLINE,
                width=2.5 if is_selected else 2,
            )


def redraw_all(canvas, nodes, selected_node=None):
    canvas.delete("node")
    for idx, node in enumerate(nodes):
        draw_node(canvas, node, f"node_{idx}", selected=(node is selected_node))


class CreateItemTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Create Mod Item Tracker")
        self.root.geometry("1150x750")
        self.root.configure(bg=BG_COLOR)

        self.nodes = []
        self.paths = []
        self.next_id = 1
        self.drag_state = {
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

        self._build_ui()
        self._load_initial_state()

    def _build_ui(self):
        topbar = tk.Frame(self.root, bg=TOPBAR_BG, padx=12, pady=10)
        topbar.pack(side=tk.TOP, fill=tk.X)

        self.entry = tk.Entry(
            topbar,
            bg=INPUT_BG,
            fg=INPUT_FG,
            insertbackground=INPUT_FG,
            relief=tk.FLAT,
            font=("Segoe UI", 11),
            width=32,
        )
        self.entry.pack(side=tk.LEFT, ipady=6, padx=(0, 10))
        self.entry.bind("<Return>", lambda _event: self.add_item())

        add_btn = tk.Button(
            topbar,
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

        self.main_area = tk.Frame(self.root, bg=BG_COLOR)
        self.main_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self._build_side_panel()

        self.canvas = tk.Canvas(
            self.main_area,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

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

        # Support right-click across Windows/Linux (<Button-3>) and macOS (<Button-2> / Ctrl-Click)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click)
        self.canvas.bind("<ButtonPress-2>", self.on_right_click)
        self.canvas.bind("<Control-Button-1>", self.on_right_click)

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

    def _load_initial_state(self):
        loaded_nodes, loaded_paths = load_data()
        self.paths = loaded_paths
        for entry in loaded_nodes:
            node = {
                "name": entry["name"],
                "x": entry["x"],
                "y": entry["y"],
            }
            tag = f"node_{self.next_id}"
            self.next_id += 1
            draw_node(self.canvas, node, tag)
            self.nodes.append(node)

    def _save_state(self):
        save_data(self.nodes, self.paths)

    def _find_node_at(self, x, y):
        overlapping = self.canvas.find_overlapping(x, y, x, y)
        for item_id in reversed(overlapping):
            tags = self.canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith("node_"):
                    for node in self.nodes:
                        if node.get("tag") == tag:
                            return node
        return None

    def _next_spawn_position(self):
        self.root.update_idletasks()
        w = max(self.canvas.winfo_width(), 400)
        h = max(self.canvas.winfo_height(), 300)
        offset = (len(self.nodes) % 8) * 28
        x = w / 2 - 100 + offset
        y = h / 2 - 80 + offset
        return x, y

    def select_node(self, node):
        if node is None:
            self.close_side_panel()
            return

        node_changed = node is not self.selected_node
        self.selected_node = node
        update_node_selection_visuals(self.canvas, self.nodes, self.selected_node)

        if not self.side_panel.winfo_ismapped():
            self.side_panel.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)

        self.panel_title_label.configure(text=node["name"])
        if node_changed and self.form_visible:
            self.hide_add_path_form()
        self.refresh_side_panel_paths()

    def close_side_panel(self):
        self.selected_node = None
        update_node_selection_visuals(self.canvas, self.nodes, None)
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
        method = self.method_entry.get().strip()
        inputs = parse_comma_separated(self.inputs_entry.get())
        outputs = parse_comma_separated(self.outputs_entry.get())

        if not method:
            messagebox.showwarning("Missing Method", "Please enter a method name.", parent=self.root)
            return
        if not inputs:
            messagebox.showwarning("Missing Inputs", "Please enter at least one input item.", parent=self.root)
            return
        if not outputs:
            messagebox.showwarning("Missing Outputs", "Please enter at least one output item.", parent=self.root)
            return

        self.paths.append(
            {
                "method": method,
                "inputs": inputs,
                "outputs": outputs,
            }
        )
        self._save_state()
        self.hide_add_path_form()
        self.refresh_side_panel_paths()

    def delete_path(self, path_obj):
        self.paths = [p for p in self.paths if p is not path_obj]
        self._save_state()
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

            text_label = tk.Label(
                card,
                text=format_path(path_obj),
                bg=CARD_BG,
                fg=NODE_TEXT,
                font=("Segoe UI", 10),
                anchor="w",
                justify=tk.LEFT,
                wraplength=PANEL_WIDTH - 135,
            )
            text_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.paths_canvas.yview_moveto(0)
        self._sync_paths_scrollregion()

    def add_item(self):
        name = self.entry.get().strip()
        if not name:
            return

        if any(node["name"].lower() == name.lower() for node in self.nodes):
            messagebox.showwarning(
                "Duplicate Item",
                f'"{name}" already exists.',
                parent=self.root,
            )
            return

        x, y = self._next_spawn_position()
        node = {"name": name, "x": x, "y": y}
        tag = f"node_{self.next_id}"
        self.next_id += 1

        draw_node(self.canvas, node, tag)
        self.nodes.append(node)
        self._save_state()

        self.entry.delete(0, tk.END)
        self.entry.focus_set()

    def on_left_press(self, event):
        self.context_menu.unpost()
        node = self._find_node_at(event.x, event.y)
        if node is None:
            self.drag_state = {
                "node": None,
                "start_x": 0,
                "start_y": 0,
                "last_x": 0,
                "last_y": 0,
                "dragging": False,
            }
            return

        self.canvas.tag_raise(node["tag"])
        self.drag_state = {
            "node": node,
            "start_x": event.x,
            "start_y": event.y,
            "last_x": event.x,
            "last_y": event.y,
            "dragging": False,
        }

    def on_left_drag(self, event):
        node = self.drag_state["node"]
        if node is None:
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

        self.canvas.move(node["tag"], dx, dy)
        node["x"] += dx
        node["y"] += dy
        self.drag_state["last_x"] = event.x
        self.drag_state["last_y"] = event.y

    def on_left_release(self, _event):
        node = self.drag_state["node"]
        was_dragging = self.drag_state["dragging"]
        self.drag_state = {
            "node": None,
            "start_x": 0,
            "start_y": 0,
            "last_x": 0,
            "last_y": 0,
            "dragging": False,
        }

        if node is not None:
            if was_dragging:
                self._save_state()
            else:
                self.select_node(node)

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
        if node is self.selected_node:
            self.close_side_panel()
        self.canvas.delete(node["tag"])
        self.nodes = [n for n in self.nodes if n is not node]
        self._save_state()


def main():
    root = tk.Tk()
    CreateItemTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
