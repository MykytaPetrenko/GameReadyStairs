bl_info = {
    "name": "Modular Stair Generator",
    "author": "Codex",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Add > Mesh > Modular Stairs",
    "description": "Generate merged modular stairs running from the origin along negative Y.",
    "category": "Add Mesh",
}

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
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


def _step_profile(step_index, tread, riser, has_layer, layer_z_offset, is_simple):
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

    if has_layer and layer_z_offset > EPSILON:
        points["F"] = (y_front, z_under_front - layer_z_offset)
        points["G"] = (y_back, z_base - layer_z_offset)
        cap_faces.insert(0, ("F", "A", "E", "G"))
        outer_edges.extend((("E", "G"), ("G", "F"), ("F", "A")))
    else:
        outer_edges.append(("E", "A"))

    return {
        "points": points,
        "cap_faces": tuple(cap_faces),
        "outer_edges": tuple(outer_edges),
    }


def build_stair_mesh(name, step_count, width, riser, tread, stair_type, layer_z_offset, simple_start, simple_end):
    half_width = width * 0.5
    has_layer = stair_type == "LAYER"
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
            has_layer,
            layer_z_offset,
            is_simple,
        )

        left = {
            name: vertex_for(point, -half_width)
            for name, point in profile["points"].items()
        }
        right = {
            name: vertex_for(point, half_width)
            for name, point in profile["points"].items()
        }

        for cap_face in profile["cap_faces"]:
            _add_face([left[name] for name in cap_face], faces, face_lookup)
            _add_face([right[name] for name in reversed(cap_face)], faces, face_lookup)

        for edge_start, edge_end in profile["outer_edges"]:
            _add_face(
                [
                    left[edge_start],
                    left[edge_end],
                    right[edge_end],
                    right[edge_start],
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
    stair_type: EnumProperty(
        name="Type",
        description="Choose the base stair topology",
        items=(
            ("BASIC", "Type 1", "Base stair with the additional lower triangle"),
            ("LAYER", "Type 2 - Extra Layer", "Base stair with an extra lower offset layer"),
        ),
        default="BASIC",
    )
    layer_z_offset: FloatProperty(
        name="Layer Z Offset",
        description="Vertical offset of the extra lower layer for Type 2 stairs",
        default=0.08,
        min=0.0,
        unit="LENGTH",
    )
    simple_start: BoolProperty(
        name="Simple Start",
        description="Make the first step rectangular, without the lower triangle or extra layer",
        default=False,
    )
    simple_end: BoolProperty(
        name="Simple End",
        description="Make the last step rectangular, without the lower triangle or extra layer",
        default=False,
    )

    def execute(self, context):
        mesh = build_stair_mesh(
            "Modular_Stairs_Mesh",
            self.step_count,
            self.width,
            self.riser,
            self.tread,
            self.stair_type,
            self.layer_z_offset,
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
