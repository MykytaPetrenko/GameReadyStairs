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
