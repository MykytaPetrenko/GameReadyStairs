bl_info = {
    "name": "Modular Stair Generator",
    "author": "Codex",
    "version": (1, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Add > Mesh > Modular Stairs",
    "description": "Generate merged modular stairs running from the origin along negative Y.",
    "category": "Add Mesh",
}

import bmesh
import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty
from bpy.types import Operator
from bpy_extras.object_utils import AddObjectHelper, object_data_add


EPSILON = 0.000001


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
    if len(set(indices)) != len(indices):
        return

    key = tuple(sorted(indices))
    if key in face_lookup:
        return

    face_lookup.add(key)
    faces.append(indices)


def _step_profile(step_index, tread, riser, use_lower_slab, lower_slab_z_offset, is_simple):
    y_front = -step_index * tread
    y_back = -(step_index + 1) * tread
    z_base = step_index * riser
    z_top = (step_index + 1) * riser

    if is_simple:
        return {
            "points": {
                "B": (y_front, z_base),
                "C": (y_front, z_top),
                "D": (y_back, z_top),
                "E": (y_back, z_base),
            },
            "cap_faces": (("B", "C", "D", "E"),),
            "outer_edges": (("B", "C"), ("C", "D"), ("D", "E"), ("E", "B")),
            "bottom_edge": None,
        }

    z_under_front = z_base - riser
    points = {
        "A": (y_front, z_under_front),
        "B": (y_front, z_base),
        "C": (y_front, z_top),
        "D": (y_back, z_top),
        "E": (y_back, z_base),
    }
    cap_faces = [("A", "B", "E"), ("B", "C", "D", "E")]
    outer_edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "E")]

    if use_lower_slab and lower_slab_z_offset > EPSILON:
        points["F"] = (y_front, z_under_front - lower_slab_z_offset)
        points["G"] = (y_back, z_base - lower_slab_z_offset)
        cap_faces.insert(0, ("F", "A", "E", "G"))
        outer_edges.extend((("E", "G"), ("G", "F"), ("F", "A")))
        bottom_edge = ("G", "F")
    else:
        outer_edges.append(("E", "A"))
        bottom_edge = ("E", "A")

    return {
        "points": points,
        "cap_faces": tuple(cap_faces),
        "outer_edges": tuple(outer_edges),
        "bottom_edge": bottom_edge,
    }


def _reinforcement_width(total_width, requested_width):
    maximum_width = total_width * 0.5 - EPSILON
    if maximum_width <= EPSILON:
        return 0.0
    return min(max(requested_width, 0.0), maximum_width)


def _reinforcement_x_values(half_width, rib_width):
    if rib_width <= EPSILON:
        return (-half_width, half_width)
    return (
        -half_width,
        -half_width + rib_width,
        half_width - rib_width,
        half_width,
    )


def build_stair_mesh(
    name,
    step_count,
    width,
    riser,
    tread,
    use_lower_slab,
    lower_slab_z_offset,
    use_side_ribs,
    rib_width,
    rib_z_offset,
    cut_top,
    simple_start,
    simple_end,
):
    half_width = width * 0.5
    rib_width = _reinforcement_width(width, rib_width)
    can_build_ribs = use_side_ribs and rib_width > EPSILON and rib_z_offset > EPSILON
    rib_x_values = _reinforcement_x_values(half_width, rib_width)
    full_x_values = (-half_width, half_width)
    vertices = []
    faces = []
    vertex_lookup = {}
    face_lookup = set()

    def vertex_for(point, x_value):
        y_value, z_value = point
        return _add_vertex((x_value, y_value, z_value), vertices, vertex_lookup)

    for step_index in range(step_count):
        is_simple = (step_index == 0 and simple_start) or (
            step_index == step_count - 1 and simple_end
        )
        profile = _step_profile(
            step_index,
            tread,
            riser,
            use_lower_slab,
            lower_slab_z_offset,
            is_simple,
        )

        def vertices_for_names(names, x_value):
            return [vertex_for(profile["points"][point_name], x_value) for point_name in names]

        for cap_face in profile["cap_faces"]:
            _add_face(vertices_for_names(cap_face, -half_width), faces, face_lookup)
            _add_face(vertices_for_names(reversed(cap_face), half_width), faces, face_lookup)

        for edge_start, edge_end in profile["outer_edges"]:
            x_values = full_x_values
            if can_build_ribs and profile["bottom_edge"] == (edge_start, edge_end):
                x_values = rib_x_values
            elif can_build_ribs and cut_top:
                x_values = rib_x_values

            for x_start, x_end in zip(x_values, x_values[1:]):
                _add_face(
                    [
                        vertex_for(profile["points"][edge_start], x_start),
                        vertex_for(profile["points"][edge_end], x_start),
                        vertex_for(profile["points"][edge_end], x_end),
                        vertex_for(profile["points"][edge_start], x_end),
                    ],
                    faces,
                    face_lookup,
                )

        if can_build_ribs and profile["bottom_edge"] and not is_simple:
            bottom_start, bottom_end = profile["bottom_edge"]
            for outer_x, inner_x in (
                (-half_width, -half_width + rib_width),
                (half_width, half_width - rib_width),
            ):
                start_outer = vertex_for(profile["points"][bottom_start], outer_x)
                start_inner = vertex_for(profile["points"][bottom_start], inner_x)
                end_outer = vertex_for(profile["points"][bottom_end], outer_x)
                end_inner = vertex_for(profile["points"][bottom_end], inner_x)

                start_y, start_z = profile["points"][bottom_start]
                end_y, end_z = profile["points"][bottom_end]
                start_outer_down = _add_vertex(
                    (outer_x, start_y, start_z - rib_z_offset),
                    vertices,
                    vertex_lookup,
                )
                start_inner_down = _add_vertex(
                    (inner_x, start_y, start_z - rib_z_offset),
                    vertices,
                    vertex_lookup,
                )
                end_outer_down = _add_vertex(
                    (outer_x, end_y, end_z - rib_z_offset),
                    vertices,
                    vertex_lookup,
                )
                end_inner_down = _add_vertex(
                    (inner_x, end_y, end_z - rib_z_offset),
                    vertices,
                    vertex_lookup,
                )

                _add_face(
                    [start_outer_down, end_outer_down, end_inner_down, start_inner_down],
                    faces,
                    face_lookup,
                )
                _add_face(
                    [start_outer, start_outer_down, start_inner_down, start_inner],
                    faces,
                    face_lookup,
                )
                _add_face(
                    [end_inner, end_inner_down, end_outer_down, end_outer],
                    faces,
                    face_lookup,
                )
                _add_face(
                    [start_outer, end_outer, end_outer_down, start_outer_down],
                    faces,
                    face_lookup,
                )
                _add_face(
                    [start_inner, start_inner_down, end_inner_down, end_inner],
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
        default=8,
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
        description="Vertical rise of one step",
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
    use_lower_slab: BoolProperty(
        name="Lower Slab",
        description="Add a lower offset slab under regular stair modules",
        default=False,
    )
    lower_slab_z_offset: FloatProperty(
        name="Slab Z Offset",
        description="Vertical offset of the lower slab",
        default=0.08,
        min=0.0,
        unit="LENGTH",
    )
    use_side_ribs: BoolProperty(
        name="Side Ribs",
        description="Add reinforcement ribs under both side edges of regular stair modules",
        default=False,
    )
    rib_width: FloatProperty(
        name="Rib Width",
        description="Width of each side reinforcement rib measured inward from the side",
        default=0.15,
        min=0.001,
        unit="LENGTH",
    )
    rib_z_offset: FloatProperty(
        name="Rib Z Offset",
        description="Downward extrusion distance for the side reinforcement ribs",
        default=0.08,
        min=0.0,
        unit="LENGTH",
    )
    cut_top: BoolProperty(
        name="Cut Top",
        description="Continue the rib edge loops through the full stair surface",
        default=False,
    )
    simple_start: BoolProperty(
        name="Simple Start",
        description="Make the first step rectangular, without the lower triangle, lower slab, or side ribs",
        default=False,
    )
    simple_end: BoolProperty(
        name="Simple End",
        description="Make the last step rectangular, without the lower triangle, lower slab, or side ribs",
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "step_count")
        layout.prop(self, "width")
        layout.prop(self, "riser")
        layout.prop(self, "tread")

        layout.separator()
        layout.prop(self, "use_lower_slab")
        slab_box = layout.column()
        slab_box.enabled = self.use_lower_slab
        slab_box.prop(self, "lower_slab_z_offset")

        layout.separator()
        layout.prop(self, "use_side_ribs")
        rib_box = layout.column()
        rib_box.enabled = self.use_side_ribs
        rib_box.prop(self, "rib_width")
        rib_box.prop(self, "rib_z_offset")
        rib_box.prop(self, "cut_top")

        layout.separator()
        layout.prop(self, "simple_start")
        layout.prop(self, "simple_end")

    def execute(self, context):
        mesh = build_stair_mesh(
            "Modular_Stairs_Mesh",
            self.step_count,
            self.width,
            self.riser,
            self.tread,
            self.use_lower_slab,
            self.lower_slab_z_offset,
            self.use_side_ribs,
            self.rib_width,
            self.rib_z_offset,
            self.cut_top,
            self.simple_start,
            self.simple_end,
        )
        obj = object_data_add(context, mesh, operator=self)
        obj.name = "Modular Stairs"
        obj.location = (0.0, 0.0, 0.0)

        if not obj.data.materials:
            material = bpy.data.materials.new("Stair Concrete")
            material.diffuse_color = (0.55, 0.55, 0.52, 1.0)
            obj.data.materials.append(material)

        return {"FINISHED"}


def add_stairs_menu(self, context):
    self.layout.operator(
        MODULAR_ASSETS_OT_add_stairs.bl_idname,
        text="Modular Stairs",
        icon="MESH_CUBE",
    )


classes = (
    MODULAR_ASSETS_OT_add_stairs,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_mesh_add.append(add_stairs_menu)


def unregister():
    bpy.types.VIEW3D_MT_mesh_add.remove(add_stairs_menu)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
