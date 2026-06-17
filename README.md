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
