bl_info = {
    "name": "Node Editor Pro",
    "author": "Bruno Torres Martín",
    "version": (0, 4),
    "blender": (4, 5, 0),
    "location": "Node Editor > Sidebar (N)",
    "description": "Custom notes and organization utilities for all Node Editors with adjustable grid, connection-based auto-layout, live snap movement, optional stats and orphan cleanup",
    "warning": "",
    "category": "Node",
    "tracker_url": "https://github.com/the-visual-geek/Node-Editor-Pro-Add-on/issues",
}

import bpy
import math
from bpy.types import Node, PropertyGroup
from bpy.props import StringProperty, BoolProperty, PointerProperty, FloatProperty

DEFAULT_NOTE_COLOR = (0.1882353, 0.1882353, 0.1882353)
COL_PADDING = 60.0
ROW_PADDING = 40.0

# ----------------------------
# Helpers
# ----------------------------
def node_size(n):
    w = getattr(n, "width", 140.0)
    try:
        h = float(n.dimensions.y)
    except Exception:
        h = 100.0
    return w, h

def get_node_level(node, visited=None):
    if visited is None:
        visited = set()
    if node in visited:
        return 0
    visited.add(node)

    if not node.inputs:
        return 0

    levels = []
    for inp in node.inputs:
        if inp.is_linked:
            from_node = inp.links[0].from_node
            levels.append(get_node_level(from_node, visited) + 1)
    return max(levels) if levels else 0

# ----------------------------
# Snap Movement Handler
# ----------------------------
_snap_running = False
_snap_timer = None

def snap_movement_handler(scene):
    props = scene.sep_settings
    if not props.snap_movement:
        return

    area = None
    for a in bpy.context.screen.areas:
        if a.type == "NODE_EDITOR":
            area = a
            break
    if not area:
        return

    space = area.spaces.active
    if not space or space.type != "NODE_EDITOR" or not space.node_tree:
        return

    for n in space.node_tree.nodes:
        if n.select:
            n.location.x = round(n.location.x / props.grid_x) * props.grid_x
            n.location.y = round(n.location.y / props.grid_y) * props.grid_y

def toggle_snap_movement(self, context):
    global _snap_running, _snap_timer

    if self.snap_movement and not _snap_running:
        wm = context.window_manager
        _snap_timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(NODE_OT_snap_movementModal())
        _snap_running = True

    elif not self.snap_movement and _snap_running:
        wm = context.window_manager
        if _snap_timer:
            wm.event_timer_remove(_snap_timer)
        _snap_running = False

# ----------------------------
# Propiedades
# ----------------------------
class SEP_Settings(PropertyGroup):
    layout_only_selected: BoolProperty(
        name="Only selected",
        description="Apply only to selected nodes (Organize + Snap)",
        default=True,
    )
    grid_x: FloatProperty(
        name="Grid X",
        description="Grid spacing in X direction",
        default=100.0,
        min=10.0,
        max=500.0,
    )
    grid_y: FloatProperty(
        name="Grid Y",
        description="Grid spacing in Y direction",
        default=40.0,
        min=10.0,
        max=500.0,
    )
    use_connection_layout: BoolProperty(
        name="Use Connection Layout",
        description="Organize nodes left to right following their connections",
        default=False,
    )
    snap_movement: BoolProperty(
        name="Snap Movement",
        description="Snap nodes to grid while moving them in real time",
        default=False,
        update=toggle_snap_movement,
    )
    show_stats: BoolProperty(
        name="Show Stats",
        description="Enable node tree statistics (may slow down with large node trees)",
        default=False,
    )

# ----------------------------
# Nodo Nota
# ----------------------------
class CustomNoteNode(Node):
    bl_idname = "CustomNodeTypeNote"
    bl_label = "Note"
    bl_icon = "FILE_TEXT"
    bl_tree_type = 'NodeTree'  # <-- CAMBIO (ahora funciona en todos los node editors)

    note_text: StringProperty(
        name="Note",
        description="Text of the note",
        default="Write your note here...",
    )

    def init(self, context):
        self.width = 200
        self.use_custom_color = True
        self.color = DEFAULT_NOTE_COLOR

    def draw_buttons(self, context, layout):
        layout.prop(self, "note_text", text="")

    def draw_label(self):
        return self.bl_label

# ----------------------------
# Operadores
# ----------------------------
class NODE_OT_snap_and_organize(bpy.types.Operator):
    bl_idname = "node.snap_and_organize"
    bl_label = "Organize Nodes"
    bl_description = "Align nodes to grid and organize them in a smart layout"

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'NODE_EDITOR':
            self.report({'WARNING'}, "Not in Node Editor")
            return {'CANCELLED'}

        node_tree = space.node_tree
        if not node_tree:
            self.report({'WARNING'}, "No active node tree")
            return {'CANCELLED'}

        props = context.scene.sep_settings
        nodes = node_tree.nodes
        if props.layout_only_selected:
            nodes = [n for n in nodes if n.select]
        else:
            nodes = list(nodes)

        if not nodes:
            return {'FINISHED'}

        # Snap inicial
        for n in nodes:
            n.location.x = round(n.location.x / props.grid_x) * props.grid_x
            n.location.y = round(n.location.y / props.grid_y) * props.grid_y

        # NORMALIZAR antes de organizar
        min_x = min(n.location.x for n in nodes)
        max_y = max(n.location.y for n in nodes)
        for n in nodes:
            n.location.x -= min_x
            n.location.y -= max_y

        # Organize
        if props.use_connection_layout:
            levels = {n: get_node_level(n) for n in nodes}
            max_level = max(levels.values())
            cols = [[] for _ in range(max_level + 1)]
            for n, lvl in levels.items():
                cols[lvl].append(n)

            x = 0
            for col_nodes in cols:
                if not col_nodes:
                    x += props.grid_x + COL_PADDING
                    continue

                total_height = sum(node_size(n)[1] for n in col_nodes) + (len(col_nodes) - 1) * ROW_PADDING
                y = total_height / 2.0

                for n in col_nodes:
                    w, h = node_size(n)
                    n.location.x = round(x / props.grid_x) * props.grid_x
                    n.location.y = round(y / props.grid_y) * props.grid_y
                    y -= h + ROW_PADDING

                max_w = max(node_size(n)[0] for n in col_nodes)
                x += max_w + COL_PADDING

        else:
            nodes_sorted = sorted(nodes, key=lambda n: n.location.x)
            count = len(nodes_sorted)
            rows = math.ceil(math.sqrt(count))
            cols = math.ceil(count / rows)

            col_widths = [0.0] * cols
            row_heights = [0.0] * rows
            node_grid_pos = []

            for idx, n in enumerate(nodes_sorted):
                col = idx // rows
                row = idx % rows
                w, h = node_size(n)
                col_widths[col] = max(col_widths[col], w)
                row_heights[row] = max(row_heights[row], h)
                node_grid_pos.append((n, col, row, w, h))

            start_x = 0
            start_y = 0
            x_offsets = [start_x]
            for c in range(1, cols):
                x_offsets.append(x_offsets[c - 1] + col_widths[c - 1] + COL_PADDING)

            def row_y(row_idx):
                return start_y - sum(row_heights[:row_idx]) - (row_idx * ROW_PADDING)

            for (n, c, r, w, h) in node_grid_pos:
                x = x_offsets[c]
                y = row_y(r)
                n.location.x = round(x / props.grid_x) * props.grid_x
                n.location.y = round(y / props.grid_y) * props.grid_y

        return {'FINISHED'}

class NODE_OT_snap_movementModal(bpy.types.Operator):
    """Mantiene los nodos alineados mientras se mueven"""
    bl_idname = "node.snap_movement_modal"
    bl_label = "Snap Movement Modal"

    _timer = None

    def modal(self, context, event):
        props = context.scene.sep_settings
        if not props.snap_movement:
            return {'CANCELLED'}

        if event.type == 'TIMER':
            snap_movement_handler(context.scene)

        if not context.area:
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class NODE_OT_cleanup_orphans(bpy.types.Operator):
    """Remove all orphan (disconnected) nodes"""
    bl_idname = "node.cleanup_orphans"
    bl_label = "Clean Orphan Nodes"
    bl_description = "Deletes all nodes without any input or output connections"

    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'NODE_EDITOR':
            self.report({'WARNING'}, "Not in Node Editor")
            return {'CANCELLED'}

        node_tree = space.node_tree
        if not node_tree:
            self.report({'WARNING'}, "No active node tree")
            return {'CANCELLED'}

        removed = 0
        for node in list(node_tree.nodes):
            has_input = any(inp.is_linked for inp in node.inputs)
            has_output = any(out.is_linked for out in node.outputs)
            if not has_input and not has_output:
                node_tree.nodes.remove(node)
                removed += 1

        self.report({'INFO'}, f"Removed {removed} orphan nodes")
        return {'FINISHED'}

# ----------------------------
# Panel
# ----------------------------
class NODE_PT_shader_editor_pro(bpy.types.Panel):
    bl_label = "Node Editor Pro"
    bl_idname = "NODE_PT_shader_editor_pro"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Node Editor Pro'

    @classmethod
    def poll(cls, context):
        area = context.area
        return area and area.type == 'NODE_EDITOR'

    def draw(self, context):
        layout = self.layout
        props = context.scene.sep_settings

        col = layout.column(align=True)
        col.label(text="Notes:")
        col.operator("node.add_node", text="Add Note", icon="FILE_TEXT").type = "CustomNodeTypeNote"

        layout.separator()

        layout.label(text="Cleanup:")
        layout.operator("node.cleanup_orphans", icon="TRASH")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="Organize Nodes:")
        col.prop(props, "layout_only_selected")
        col.prop(props, "grid_x")
        col.prop(props, "grid_y")
        col.prop(props, "use_connection_layout")
        col.operator("node.snap_and_organize", icon="GRID")

        layout.separator()
        col = layout.column(align=True)
        col.prop(props, "snap_movement")

        layout.separator()
        layout.prop(props, "show_stats")

        if props.show_stats:
            nodes = context.space_data.node_tree.nodes if context.space_data.node_tree else []
            total_nodes = len(nodes)
            total_links = sum(len(n.outputs) for n in nodes)
            orphan_nodes = sum(1 for n in nodes if not n.inputs and not n.outputs)
            max_depth = max((get_node_level(n) for n in nodes), default=0)

            layout.label(text="Node Tree Stats:")
            box = layout.box()
            box.label(text=f"Total nodes: {total_nodes}")
            box.label(text=f"Connections: {total_links}")
            box.label(text=f"Orphan nodes: {orphan_nodes}")
            box.label(text=f"Max depth: {max_depth}")

        layout.separator()
        layout.label(text="Shortcuts:")
        box2 = layout.box()
        box2.label(text="Shift + O → Organize & Snap")
        box2.label(text="Shift + S → Toggle Snap Movement")
        box2.label(text="Shift + C → Clean Orphan Nodes")

# ----------------------------
# Menú Add
# ----------------------------
def add_custom_node_button(self, context):
    op = self.layout.operator("node.add_node", text="Note", icon="FILE_TEXT")
    op.type = "CustomNodeTypeNote"
    op.use_transform = True
    self.layout.operator_context = 'INVOKE_DEFAULT'

# ----------------------------
# Keymaps
# ----------------------------
addon_keymaps = []

def register_keymaps():
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')

    kmi = km.keymap_items.new("node.snap_and_organize", type='O', value='PRESS', shift=True)
    addon_keymaps.append((km, kmi))

    kmi = km.keymap_items.new("wm.context_toggle", type='S', value='PRESS', shift=True)
    kmi.properties.data_path = "scene.sep_settings.snap_movement"
    addon_keymaps.append((km, kmi))

    kmi = km.keymap_items.new("node.cleanup_orphans", type='C', value='PRESS', shift=True)
    addon_keymaps.append((km, kmi))

def unregister_keymaps():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

# ----------------------------
# Registro
# ----------------------------
classes = (
    SEP_Settings,
    CustomNoteNode,
    NODE_OT_snap_and_organize,
    NODE_OT_snap_movementModal,
    NODE_OT_cleanup_orphans,
    NODE_PT_shader_editor_pro,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sep_settings = PointerProperty(type=SEP_Settings)
    bpy.types.NODE_MT_add.append(add_custom_node_button)
    register_keymaps()

def unregister():
    unregister_keymaps()
    bpy.types.NODE_MT_add.remove(add_custom_node_button)
    del bpy.types.Scene.sep_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
