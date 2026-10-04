# Assembly Workbench and 3MF Export

Verified on FreeCAD 1.1.4. The joint code was run in the GUI session through the MCP
`execute_code` tool; `JointObject` and `UtilsAssembly` also import under `freecadcmd`, but
joint creation was only exercised in the GUI.

## Assembly structure

```
Assembly (Assembly::AssemblyObject, Type = "Assembly")
├── Joints (Assembly::JointGroup)
│   ├── GroundedJoint, Fixed, Revolute, ...   (App::FeaturePython)
├── <Part>Link (App::Link -> LinkedObject = the PartDesign Body)
└── <Part>Link ...
```

Model each part as its own `PartDesign::Body`, link it into the assembly with `App::Link`,
ground one part, then add joints between faces/vertices of the links.

## Reference format (silent failure if wrong)

A joint reference is `[link, [element, vertex]]` where the sub-names are **object names**
joined by dots, relative to the link: `"<BodyName>.<FeatureName>.<FaceN>"`, for example
`["Block.Pad.Face5", "Block.Pad.Vertex1"]`. The first entry picks the face (orientation),
the second the vertex (origin of the joint coordinate system).

A wrong form such as `"Pad.Face5."` is **accepted without an error**: the joint coordinate
systems silently fall back to identity and the solver reports success while placing the parts
at their origins. Always check, after solving, that `joint.Placement1`/`Placement2` are
non-trivial and that the bounding box is where you expect.

```python
import FreeCAD as App
import FreeCADGui as Gui          # assembly joint creation: run in the GUI session
import Part, Sketcher
import JointObject
V = App.Vector

doc = App.newDocument("Asm")

def make_part(name, w, d, h):
    body = doc.addObject("PartDesign::Body", name)
    xy = next(o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    pts = [(0, 0), (w, 0), (w, d), (0, d)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sk
    pad.Length = h
    doc.recompute()
    return body

base = make_part("Base", 40, 40, 10)
block = make_part("Block", 20, 20, 10)

asm = doc.addObject("Assembly::AssemblyObject", "Assembly")
asm.Type = "Assembly"
joints = asm.newObject("Assembly::JointGroup", "Joints")

base_link = asm.newObject("App::Link", "BaseLink")
base_link.LinkedObject = base
base_link.Label = "BaseLink"
block_link = asm.newObject("App::Link", "BlockLink")
block_link.LinkedObject = block
block_link.Label = "BlockLink"
block_link.Placement.Base = V(100, 50, 0)            # starting position; the solver moves it

ground = joints.newObject("App::FeaturePython", "GroundedJoint")
JointObject.GroundedJoint(ground, base_link)         # the fixed reference part
doc.recompute()
```

## Choosing faces and vertices by geometry

Names like `Face6`/`Vertex2` change when a part changes; select them from the shape.

```python
def face_and_vertex(body, want_face, want_vertex):
    """('FaceN', 'VertexM'): a face matching want_face and a vertex of that face matching want_vertex."""
    shape = body.Shape
    fi = next(i for i, f in enumerate(shape.Faces) if want_face(f))
    face = shape.Faces[fi]
    vi = next(i for i, v in enumerate(shape.Vertexes)
              if want_vertex(v.Point) and any(v.Point.distanceToPoint(fv.Point) < 1e-6 for fv in face.Vertexes))
    return f"Face{fi + 1}", f"Vertex{vi + 1}"

top = lambda f: abs(f.CenterOfMass.z - 10) < 1e-6 and f.normalAt(0, 0).z > 0.9
bottom = lambda f: abs(f.CenterOfMass.z) < 1e-6 and f.normalAt(0, 0).z < -0.9
at_origin = lambda p: abs(p.x) < 1e-6 and abs(p.y) < 1e-6

fa, va = face_and_vertex(base, top, at_origin)        # top of Base, corner at the origin
fb, vb = face_and_vertex(block, bottom, at_origin)    # bottom of Block, the same corner

JT_FIXED, JT_REVOLUTE = 0, 1                          # index into JointObject.JointTypes
joint = joints.newObject("App::FeaturePython", "Fixed")
JointObject.Joint(joint, JT_FIXED)
joint.Proxy.setJointConnectors(joint, [
    [block_link, [f"Block.Pad.{fb}", f"Block.Pad.{vb}"]],     # moving part first
    [base_link, [f"Base.Pad.{fa}", f"Base.Pad.{va}"]],        # fixed/reference part second
])
doc.recompute()
asm.solve()                                           # 0 on success
doc.recompute()

bb = block_link.Shape.BoundBox
print(bb.ZMin, bb.ZMax)                               # 10.0 20.0: Block rests on top of Base
print(joint.Placement2.Base)                          # (0, 0, 10): not identity, so the reference resolved
```

Joint types (`JointObject.JointTypes`): Fixed, Revolute, Cylindrical, Slider, Ball, Distance,
Parallel, Perpendicular, Angle, RackPinion, Screw, Gears, Belt.

## Orientation, offsets, flipping

- Joint coordinate systems are made to coincide, so two faces with opposite outward normals
  can interpenetrate or end up on the wrong side. If a part lands inside or below its mate,
  call `joint.Proxy.flipOnePart(joint)`, re-solve, and re-check the bounding box. Calling it
  twice returns to the original (verified: block z 10..20, flipped, back to 10..20).
- `joint.Offset2 = App.Placement(V(5, 0, 0), App.Rotation())` shifts the mate (verified: the
  block moved 5 mm in X after solving).
- A Revolute joint leaves its rotation free: setting `joint.Angle` did not move the part.
  To pose a mechanism, use an `Angle` joint or an offset rotation (not tested here).
- Expressions on joint properties are accepted (`joint.setExpression("Angle", "VarSet.Opening")`
  set the value), so VarSet properties can drive joints; check that the solved pose changes.
- `asm.solve()` returning 0 means the solver ran, not that the layout is right. Verify.

## Assemblies and VarSets

Parts keep their own VarSet-driven dimensions. Put assembly-level values (spacing, angles,
clearances) in a VarSet in the same document and bind joint offsets to them with expressions.
After changing a VarSet value: `doc.recompute()`, `asm.solve()`, `doc.recompute()`.
Parts that are in other documents need external links; that case is not covered here.

## 3MF export for 3D printing

3MF files from FreeCAD are in millimetres (`unit="millimeter"` in the XML) and need no scale
factor in slicers.

```python
import Mesh, MeshPart

# Quick: Mesh.export accepts Part objects, Bodies, links and whole assemblies
Mesh.export([block_link, base_link], "/path/parts.3mf")      # both parts, in assembly position
Mesh.export([asm], "/path/assembly.3mf")                       # verified: 24 facets, bbox 40x40x20

# Controlled: mesh the shape yourself, then export the Mesh::Feature
shape = block.Shape                                           # a Body's shape, or any Part.Shape
mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.02, AngularDeflection=0.2)
feature = doc.addObject("Mesh::Feature", "ForPrint")
feature.Mesh = mesh
Mesh.export([feature], "/path/part.3mf")
```

Use the controlled route for printing curved parts: on a 20 mm cylinder the default export
produced 124 facets, while `LinearDeflection=0.02, AngularDeflection=0.2` produced 280. Pick
`LinearDeflection` below the printer's resolution (0.01-0.05 mm is typical); smaller values
make larger files.

Check the result before sending it to a slicer:

```python
m = Mesh.Mesh("/path/part.3mf")                  # 3MF reads back with Mesh.Mesh
print(m.isSolid(), m.hasNonManifolds(), m.Volume, m.BoundBox)
```

`isSolid()` True and no non-manifold edges is the target. Compare `m.Volume` with
`shape.Volume`, and the bounding box with the intended dimensions, to catch a unit or scale
mistake. `scripts/mesh_report.py` gives the full triage for an exported file. Existing 3MF
files (including the user's own) load with `Mesh.Mesh("file.3mf")`.

Print-oriented modelling notes: minimum wall thickness and overhang limits depend on the
printer and material; ask for them rather than assuming, and model clearances (for assembly
fits) as VarSet parameters so they can be tuned after a test print.
