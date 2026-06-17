bl_info = {
    "name": "Modular Stair Generator",
    "author": "Codex",
    "version": (2, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Add > Mesh > Modular Stairs",
    "description": "Generate modular stair top meshes running from the origin along negative Y.",
    "category": "Add Mesh",
}

import bmesh
import bpy
import json
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator
from bpy_extras.object_utils import AddObjectHelper, object_data_add


EPSILON = 0.000001
STAIR_WIDTH_EDGES_PROP = "_modular_assets_stair_core_width_edges_v2"
UP_FACE_NORMAL_Z = 0.5


def _coord_key(coord):
    return tuple(round(value, 6) for value in coord)


def _add_vertex(coord, vertices, vertex_lookup):
    key = _coord_key(coord)
    index = vertex_lookup.get(key)
    if index is None:
        index = len(vertices)
        vertices.append(coord)
        vertex_lookup[key] = index
    return index


def _add_face(indices, faces, face_lookup):
    cleaned = []
    for index in indices:
        if not cleaned or cleaned[-1] != index:
            cleaned.append(index)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()

    if len(cleaned) < 3 or len(set(cleaned)) != len(cleaned):
        return

    key = tuple(sorted(cleaned))
    if key in face_lookup:
        return

    face_lookup.add(key)
    faces.append(cleaned)


def _stair_top_polyline(step_count, tread, riser):
    points = [(0.0, 0.0)]
    for step_index in range(step_count):
        y_front = -step_index * tread
        y_back = -(step_index + 1) * tread
        z_top = (step_index + 1) * riser
        points.append((y_front, z_top))
        points.append((y_back, z_top))

    return points


def _side_offset_polyline(top_points, offset):
    last_index = len(top_points) - 1
    offset_points = []

    for index, (y_value, z_value) in enumerate(top_points):
        if index == 0:
            offset_points.append((y_value - offset, z_value))
        elif index == last_index:
            offset_points.append((y_value, z_value - offset))
        else:
            offset_points.append((y_value - offset, z_value - offset))

    return offset_points


def _profile_data(step_count, tread, riser, side_edge_offset):
    top_points = _stair_top_polyline(step_count, tread, riser)
    offset_points = _side_offset_polyline(top_points, side_edge_offset)
    boundary = top_points + list(reversed(offset_points))
    strip_faces = [
        (index, index + 1, len(top_points) + index + 1, len(top_points) + index)
        for index in range(len(top_points) - 1)
    ]
    points = top_points + offset_points
    return points, boundary, strip_faces


def _x_values(width, use_top_edge_loop, top_edge_loop_width):
    half_width = width * 0.5
    if not use_top_edge_loop:
        return (-half_width, half_width)

    loop_width = max(top_edge_loop_width, 0.0)
    loop_width = min(loop_width, half_width - EPSILON)
    if loop_width <= EPSILON:
        return (-half_width, half_width)

    return (
        -half_width,
        -half_width + loop_width,
        half_width - loop_width,
        half_width,
    )


def _edge_center_from_coords(coords):
    return tuple((coords[0][axis] + coords[1][axis]) * 0.5 for axis in range(3))


def _distance_squared(a, b):
    return sum((a[axis] - b[axis]) ** 2 for axis in range(3))


def _coords_from_edge(edge):
    return [
        [float(edge.verts[0].co[axis]) for axis in range(3)],
        [float(edge.verts[1].co[axis]) for axis in range(3)],
    ]


def _edge_is_widthwise(edge):
    first = edge.verts[0].co
    second = edge.verts[1].co
    return (
        abs(first.x - second.x) > EPSILON
        and abs(first.y - second.y) <= EPSILON
        and abs(first.z - second.z) <= EPSILON
    )


def _edge_touches_top_face(edge):
    return any(face.normal.z > UP_FACE_NORMAL_Z for face in edge.link_faces)


def _edge_x_center(edge):
    return (edge.verts[0].co.x + edge.verts[1].co.x) * 0.5


def _without_terminal_top_back_edge(edges):
    if len(edges) <= 1:
        return edges

    def profile_key(item):
        center = _edge_center_from_coords(item["vertices"])
        return (round(center[2], 6), round(-center[1], 6))

    terminal_key = max(profile_key(item) for item in edges)
    return [item for item in edges if profile_key(item) != terminal_key]


def _top_core_width_edges_from_bmesh(bm):
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    grouped_edges = {}
    for edge in bm.edges:
        if not _edge_is_widthwise(edge) or not _edge_touches_top_face(edge):
            continue

        coords = _coords_from_edge(edge)
        yz_key = (round(coords[0][1], 6), round(coords[0][2], 6))
        grouped_edges.setdefault(yz_key, []).append(edge)

    edges = []
    seen = set()
    for group in grouped_edges.values():
        edge = min(group, key=lambda item: (abs(_edge_x_center(item)), -item.calc_length()))
        coords = _coords_from_edge(edge)
        edge_key = tuple(sorted(_coord_key(coord) for coord in coords))
        if edge_key in seen:
            continue

        seen.add(edge_key)
        edges.append({"vertices": coords})

    edges = _without_terminal_top_back_edge(edges)
    edges.sort(key=lambda item: _edge_center_from_coords(item["vertices"]))
    return edges


def _generated_top_core_width_edges(step_count, tread, riser, x_values):
    top_points = _stair_top_polyline(step_count, tread, riser)
    if len(x_values) > 2:
        core_x_values = (x_values[1], x_values[-2])
    else:
        core_x_values = (x_values[0], x_values[-1])

    edges = []
    for y_value, z_value in top_points[1:-1]:
        edges.append(
            {
                "vertices": [
                    [float(core_x_values[0]), float(y_value), float(z_value)],
                    [float(core_x_values[1]), float(y_value), float(z_value)],
                ],
            }
        )
    return edges


def _store_width_edges(obj, edges):
    payload = {
        "version": 1,
        "object": obj.name,
        "edge_count": len(edges),
        "edges": edges,
    }
    obj[STAIR_WIDTH_EDGES_PROP] = json.dumps(payload)


def _load_width_edges(obj):
    raw_payload = obj.get(STAIR_WIDTH_EDGES_PROP)
    if not raw_payload:
        return []

    try:
        payload = json.loads(raw_payload)
    except (TypeError, ValueError):
        return []

    edges = []
    for item in payload.get("edges", []):
        vertices = item.get("vertices")
        if (
            isinstance(vertices, list)
            and len(vertices) == 2
            and all(isinstance(coord, list) and len(coord) == 3 for coord in vertices)
        ):
            edges.append(
                {
                    "vertices": [
                        [float(value) for value in vertices[0]],
                        [float(value) for value in vertices[1]],
                    ],
                }
            )
    return edges


def _active_mesh_object(context):
    obj = context.active_object
    if obj and obj.type == "MESH":
        return obj
    return None


def _with_object_bmesh(obj, callback):
    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(obj.data)
        result = callback(bm)
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
        return result

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        result = callback(bm)
        bm.to_mesh(obj.data)
        obj.data.update()
        return result
    finally:
        bm.free()


def build_stair_mesh(
    name,
    step_count,
    width,
    riser,
    tread,
    side_edge_offset,
    use_top_edge_loop,
    top_edge_loop_width,
):
    vertices = []
    faces = []
    vertex_lookup = {}
    face_lookup = set()

    profile_points, boundary_points, strip_faces = _profile_data(
        step_count,
        tread,
        riser,
        side_edge_offset,
    )
    x_values = _x_values(width, use_top_edge_loop, top_edge_loop_width)

    def vertex_for(x_value, point):
        y_value, z_value = point
        return _add_vertex((x_value, y_value, z_value), vertices, vertex_lookup)

    left_x = x_values[0]
    right_x = x_values[-1]
    for strip_face in strip_faces:
        _add_face(
            [vertex_for(left_x, profile_points[index]) for index in strip_face],
            faces,
            face_lookup,
        )
        _add_face(
            [vertex_for(right_x, profile_points[index]) for index in reversed(strip_face)],
            faces,
            face_lookup,
        )

    for point_index, point_start in enumerate(boundary_points):
        point_end = boundary_points[(point_index + 1) % len(boundary_points)]
        for x_start, x_end in zip(x_values, x_values[1:]):
            _add_face(
                [
                    vertex_for(x_start, point_start),
                    vertex_for(x_start, point_end),
                    vertex_for(x_end, point_end),
                    vertex_for(x_end, point_start),
                ],
                faces,
                face_lookup,
            )

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=EPSILON)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    mesh.update()
    return mesh


class MODULAR_ASSETS_OT_add_stairs(Operator, AddObjectHelper):
    bl_idname = "mesh.modular_assets_add_stairs"
    bl_label = "Modular Stairs"
    bl_options = {"REGISTER", "UNDO"}

    step_count: IntProperty(
        name="Steps",
        description="Number of stair modules to generate",
        default=3,
        min=1,
        soft_max=64,
    )
    width: FloatProperty(
        name="Width",
        description="Stair width along the X axis",
        default=2.0,
        min=0.001,
        unit="LENGTH",
    )
    riser: FloatProperty(
        name="Riser",
        description="Vertical rise between steps",
        default=0.2,
        min=0.001,
        unit="LENGTH",
    )
    tread: FloatProperty(
        name="Tread",
        description="Horizontal run of one step along negative Y",
        default=0.3,
        min=0.001,
        unit="LENGTH",
    )
    side_edge_offset: FloatProperty(
        name="Side Edge Offset",
        description="Offset distance used to create the lower side edge loop",
        default=0.08,
        min=0.001,
        unit="LENGTH",
    )
    use_top_edge_loop: BoolProperty(
        name="Top Edge Loop",
        description="Split the top mesh with width-wise edge loops near both side edges",
        default=False,
    )
    top_edge_loop_width: FloatProperty(
        name="Top Edge Loop Width",
        description="Distance of the width-wise top edge loops from each side",
        default=0.15,
        min=0.001,
        unit="LENGTH",
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "step_count")
        layout.prop(self, "width")
        layout.prop(self, "riser")
        layout.prop(self, "tread")
        layout.prop(self, "side_edge_offset")

        layout.separator()
        layout.prop(self, "use_top_edge_loop")
        loop_box = layout.column()
        loop_box.enabled = self.use_top_edge_loop
        loop_box.prop(self, "top_edge_loop_width")

    def execute(self, context):
        mesh = build_stair_mesh(
            "Modular_Stairs_Mesh",
            self.step_count,
            self.width,
            self.riser,
            self.tread,
            self.side_edge_offset,
            self.use_top_edge_loop,
            self.top_edge_loop_width,
        )
        obj = object_data_add(context, mesh, operator=self)
        obj.name = "Modular Stairs"
        obj.location = (0.0, 0.0, 0.0)
        _store_width_edges(
            obj,
            _generated_top_core_width_edges(
                self.step_count,
                self.tread,
                self.riser,
                _x_values(self.width, self.use_top_edge_loop, self.top_edge_loop_width),
            ),
        )

        if not obj.data.materials:
            material = bpy.data.materials.new("Stair Concrete")
            material.diffuse_color = (0.55, 0.55, 0.52, 1.0)
            obj.data.materials.append(material)

        return {"FINISHED"}


class MODULAR_ASSETS_OT_store_stair_width_edges(Operator):
    bl_idname = "mesh.modular_assets_store_stair_width_edges"
    bl_label = "Store Stair Core Width Edges"
    bl_description = "Store only the central core stair edges running along the width as vertex coordinate pairs"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _active_mesh_object(context) is not None

    def execute(self, context):
        obj = _active_mesh_object(context)
        edges = _with_object_bmesh(obj, _top_core_width_edges_from_bmesh)
        if not edges:
            self.report({"WARNING"}, "No core width-wise stair edges were found")
            return {"CANCELLED"}

        _store_width_edges(obj, edges)
        self.report({"INFO"}, f"Stored {len(edges)} stair core width edges")
        return {"FINISHED"}


class MODULAR_ASSETS_OT_restore_stair_width_edges(Operator):
    bl_idname = "mesh.modular_assets_restore_stair_width_edges"
    bl_label = "Restore Stair Core Edge Selection"
    bl_description = "Select the current edges whose centers are closest to stored stair core edge centers"
    bl_options = {"REGISTER", "UNDO"}

    clear_selection: BoolProperty(
        name="Clear Selection",
        description="Clear the current mesh selection before restoring the stored stair edge selection",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return _active_mesh_object(context) is not None

    def execute(self, context):
        obj = _active_mesh_object(context)
        stored_edges = _load_width_edges(obj)
        if not stored_edges:
            self.report({"WARNING"}, "No stored stair core edges were found on the active object")
            return {"CANCELLED"}

        def restore_selection(bm):
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.edges.index_update()

            if self.clear_selection:
                for vertex in bm.verts:
                    vertex.select_set(False)
                for edge in bm.edges:
                    edge.select_set(False)
                for face in bm.faces:
                    face.select_set(False)

            candidates = [
                (
                    edge,
                    tuple((edge.verts[0].co[axis] + edge.verts[1].co[axis]) * 0.5 for axis in range(3)),
                )
                for edge in bm.edges
            ]
            selected_edges = set()
            max_distance = 0.0

            for stored_edge in stored_edges:
                stored_center = _edge_center_from_coords(stored_edge["vertices"])
                nearest = sorted(
                    candidates,
                    key=lambda item: _distance_squared(stored_center, item[1]),
                )

                chosen = None
                chosen_distance = 0.0
                for candidate_edge, candidate_center in nearest:
                    if candidate_edge.index in selected_edges:
                        continue
                    chosen = candidate_edge
                    chosen_distance = _distance_squared(stored_center, candidate_center)
                    break

                if chosen is None and nearest:
                    chosen = nearest[0][0]
                    chosen_distance = _distance_squared(stored_center, nearest[0][1])

                if chosen is not None:
                    chosen.select_set(True)
                    selected_edges.add(chosen.index)
                    max_distance = max(max_distance, chosen_distance)

            bm.select_flush_mode()
            return len(selected_edges), max_distance ** 0.5

        selected_count, max_distance = _with_object_bmesh(obj, restore_selection)
        context.tool_settings.mesh_select_mode = (False, True, False)

        if obj.mode != "EDIT":
            bpy.ops.object.mode_set(mode="EDIT")

        self.report(
            {"INFO"},
            f"Restored {selected_count} stair core edges; max center distance {max_distance:.6f}",
        )
        return {"FINISHED"}


def add_stairs_menu(self, context):
    self.layout.operator(
        MODULAR_ASSETS_OT_add_stairs.bl_idname,
        text="Modular Stairs",
        icon="MESH_CUBE",
    )


def stair_width_edges_menu(self, context):
    self.layout.separator()
    self.layout.operator(
        MODULAR_ASSETS_OT_store_stair_width_edges.bl_idname,
        text="Store Stair Core Width Edges",
        icon="EDGESEL",
    )
    self.layout.operator(
        MODULAR_ASSETS_OT_restore_stair_width_edges.bl_idname,
        text="Restore Stair Core Edge Selection",
        icon="RESTRICT_SELECT_OFF",
    )


classes = (
    MODULAR_ASSETS_OT_add_stairs,
    MODULAR_ASSETS_OT_store_stair_width_edges,
    MODULAR_ASSETS_OT_restore_stair_width_edges,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_mesh_add.append(add_stairs_menu)
    bpy.types.VIEW3D_MT_edit_mesh_edges.append(stair_width_edges_menu)


def unregister():
    bpy.types.VIEW3D_MT_edit_mesh_edges.remove(stair_width_edges_menu)
    bpy.types.VIEW3D_MT_mesh_add.remove(add_stairs_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
