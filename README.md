# Modular Stair Generator

Blender add-on for generating modular stair meshes.

## Install

Use this folder as the add-on folder in Blender, then enable **Modular Stair Generator**.

The operator is available at:

`Shift+A > Mesh > Modular Stairs`

## Geometry

- Object origin: `0, 0, 0`
- Stair direction: negative `Y`
- Width axis: `X`, centered around the origin
- Height axis: `Z`
- All generated modules are created as one merged mesh object.

## Parameters

- **Steps**: number of stair modules
- **Width**: total width along `X`
- **Riser**: vertical rise per step
- **Tread**: run per step along negative `Y`
- **Type 1**: base topology with an additional lower triangle
- **Type 2 - Extra Layer**: base topology plus a lower layer offset by **Layer Z Offset**
- **Simple Start**: first step is a simple rectangle, without the lower triangle or layer
- **Simple End**: last step is a simple rectangle, without the lower triangle or layer
