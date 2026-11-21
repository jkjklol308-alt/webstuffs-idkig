import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


DATA_FILE = Path(__file__).resolve().parent / "data.json"

BG_COLOR = "#121417"
TOPBAR_BG = "#1b1f24"
INPUT_BG = "#262c34"
INPUT_FG = "#e6edf3"
BTN_BG = "#3b82f6"
BTN_ACTIVE_BG = "#2563eb"
BTN_FG = "#ffffff"

NODE_FILL = "#22272e"
NODE_OUTLINE = "#444c56"
NODE_TEXT = "#f0f6fc"
NODE_RADIUS = 12
NODE_PAD_X = 18
NODE_PAD_Y = 12
NODE_MIN_W = 110
NODE_MIN_H = 44


def load_data():
    if not DATA_FILE.exists():
        return []
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            return []
        items = []
        seen = set()
        for entry in raw:
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
            items.append({"name": name, "x": x, "y": y})
        return items
    except (OSError, json.JSONDecodeError):
        return []


def save_data(nodes):
    payload = [
        {"name": node["name"], "x": round(node["x"], 2), "y": round(node["y"], 2)}
        for node in nodes
    ]
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


def draw_node(canvas, node, tag):
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

    points = rounded_rect_points(x1, y1, x2, y2, NODE_RADIUS)
    rect_id = canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=24,
        fill=NODE_FILL,
        outline=NODE_OUTLINE,
        width=2,
        tags=(tag, "node"),
    )
    canvas.tag_raise(text_id, rect_id)

    node["tag"] = tag
    node["rect_id"] = rect_id
    node["text_id"] = text_id


def redraw_all(canvas, nodes):
    canvas.delete("node")
    for idx, node in enumerate(nodes):
        draw_node(canvas, node, f"node_{idx}")


class CreateItemTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Create Mod Item Tracker")
        self.root.geometry("1100x750")
        self.root.configure(bg=BG_COLOR)

        self.nodes = []
        self.next_id = 1
        self.drag_state = {"node": None, "last_x": 0, "last_y": 0, "moved": False}
        self.context_node = None

        self._build_ui()
        self._load_initial_nodes()

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

        self.canvas = tk.Canvas(
            self.root,
            bg=BG_COLOR,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

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

    def _load_initial_nodes(self):
        loaded = load_data()
        for entry in loaded:
            node = {
                "name": entry["name"],
                "x": entry["x"],
                "y": entry["y"],
            }
            tag = f"node_{self.next_id}"
            self.next_id += 1
            draw_node(self.canvas, node, tag)
            self.nodes.append(node)

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
        save_data(self.nodes)

        self.entry.delete(0, tk.END)
        self.entry.focus_set()

    def on_left_press(self, event):
        self.context_menu.unpost()
        node = self._find_node_at(event.x, event.y)
        if node is None:
            self.drag_state = {"node": None, "last_x": 0, "last_y": 0, "moved": False}
            return

        self.canvas.tag_raise(node["tag"])
        self.drag_state = {
            "node": node,
            "last_x": event.x,
            "last_y": event.y,
            "moved": False,
        }

    def on_left_drag(self, event):
        node = self.drag_state["node"]
        if node is None:
            return

        dx = event.x - self.drag_state["last_x"]
        dy = event.y - self.drag_state["last_y"]
        if dx == 0 and dy == 0:
            return

        self.canvas.move(node["tag"], dx, dy)
        node["x"] += dx
        node["y"] += dy
        self.drag_state["last_x"] = event.x
        self.drag_state["last_y"] = event.y
        self.drag_state["moved"] = True

    def on_left_release(self, _event):
        if self.drag_state["node"] is not None and self.drag_state["moved"]:
            save_data(self.nodes)
        self.drag_state = {"node": None, "last_x": 0, "last_y": 0, "moved": False}

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
        self.canvas.delete(node["tag"])
        self.nodes = [n for n in self.nodes if n is not node]
        save_data(self.nodes)


def main():
    root = tk.Tk()
    CreateItemTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
