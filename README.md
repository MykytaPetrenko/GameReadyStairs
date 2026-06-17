# Modular Stair Generator

Blender add-on for generating modular stair top meshes.

## Install

Use this folder as the add-on folder in Blender, then enable **Modular Stair Generator**.

The operator is available at:

`Shift+A > Mesh > Modular Stairs`

## Geometry

- Object origin: `0, 0, 0`
- Stair direction: negative `Y`
- Stair profile starts with a riser at the origin, then continues with tread/riser segments.
- Width axis: `X`, centered around the origin
- Height axis: `Z`
- The current generator creates the top stair strip and side edge offset loop as one merged mesh object.

## Parameters

- **Steps**: number of stair modules
- **Width**: total width along `X`
- **Riser**: vertical rise between steps
- **Tread**: run per step along negative `Y`
- **Side Edge Offset**: creates the lower side edge loop from the stair top polyline
- **Top Edge Loop**: adds width-wise loops near both side edges
- **Top Edge Loop Width**: distance of those width-wise loops from each side
- **Bevel**: bevels the generated stair edge loops after base mesh creation
- **Bevel Width**: bevel offset amount
- **Bevel Segments**: number of bevel segments
- **Bevel Profile**: shape of the bevel profile
- **Loop Slide**: uses Blender's loop slide behavior during bevel

## Bevel behavior

When beveling is enabled, the add-on creates the base mesh, enters Edit Mode,
clears the mesh selection, selects the central core width-wise stair edges,
expands them with Blender's edge loop selection, and then runs Blender's bevel
operator. The first bottom edge and final top-back edge are intentionally
skipped.
