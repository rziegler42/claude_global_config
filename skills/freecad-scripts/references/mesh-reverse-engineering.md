# Mesh to Parametric Model (Reverse Engineering)

Turn an STL/OBJ/3MF mesh into an editable PartDesign model whose dimensions come from a
VarSet. Verified on FreeCAD 1.1.4. `makeShapeFromMesh` + `makeSolid` gives a faceted
dumb solid; that is NOT reverse engineering and is not what the user wants.

Helper: `scripts/mesh_report.py` (triage, safe repair, primitive fitting, deviation).

```bash
freecadcmd ~/.claude/skills/freecad-scripts/scripts/mesh_report.py -- model.stl --repair --json report.json
```

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/freecad-scripts/scripts"))
import mesh_report as mr          # importing does not run anything
```

## Workflow (do the steps in order, report numbers at each)

1. **Triage** - `mr.triage(mesh)`. Check units first: a bbox under 1 mm or over 2 m is almost
   always a unit error. Read the `notes`.
2. **Repair a copy** - `mesh, log = mr.repair(mesh)`. Compare facet count and volume per step.
   Debris components, non-manifold edges and flipped normals are cheap to fix.
3. **Segment and fit** - `fits, coverage = mr.fit_primitives(mesh)`. Planes and cylinders are
   fitted and graded `good / marginal / poor`. Coverage is the fraction of facets explained.
4. **Decide the feature tree** from the fits (below), then build it.
5. **Rebuild parametrically** - VarSet properties drive sketch constraints and feature lengths.
6. **Check deviation** - `mr.deviation(mesh, body.Shape, tol=...)`. Report max, p95 and the
   fraction within tolerance. Do not call the model done without this number.
7. **Iterate** on the worst regions. Say plainly which regions are approximated.

## What to expect (measured, not assumed)

- Plane segmentation (`Mesh.getSegmentsOfType("Plane", 0.05, 30)`) is reliable.
- `Mesh.getSegmentsOfType("Cylinder", ...)` is NOT: even a perfect cylinder shatters into
  fragments and needs an absurdly loose deviation. `fit_primitives` uses a RANSAC fit on facet
  normals instead; on a clean test part it recovered radii 4.0 and 8.0 exactly.
- Many small cylinders with similar axes but drifting radii (e.g. 25-54 mm on a ring) mean
  the surface is NOT a cylinder: it is a torus, sweep or freeform. Read `quality`; do not
  rebuild each patch as its own cylinder.
- Unexplained facets (1 - coverage) are freeform: use a revolve or sweep of a measured profile
  if the part is rotationally symmetric, otherwise `ReverseEngineering.approxSurface` or the
  Surface workbench, and state that the region is approximate.
- Scans are noisy. Tolerances that work on a CAD-exported mesh are too tight for a scan; set
  `tol` from the scanner's stated accuracy and say what you chose.

## Repair: what is safe

`mr.repair` applies, in order: `removeDuplicatedPoints`, `removeDuplicatedFacets`,
`removeComponents(n)`, `harmonizeNormals`, `fixDegenerations`, `removeNonManifolds`, `fixIndices`.
On a real ring mesh this removed 30 debris facets and made it a closed solid with the volume
unchanged.

Do NOT apply these blindly: on the same mesh `removeNeedles(0.01)` deleted ~25% of the
facets, and `optimizeTopology` re-introduced self-intersections. If you call them, log the
facet and volume change and stop if either moves more than a few percent.
`fixSelfIntersections()` removed facets and left `isSolid()` False in one run: check afterwards.

## Useful Mesh / MeshPart calls (all present in 1.1.4)

```python
import Mesh, MeshPart, FreeCAD
m = Mesh.Mesh("model.stl")
m.crossSections([((0, 0, 5.0), (0, 0, 1))], 0.1)     # [(point, normal)], min_dist -> polylines per plane
m.getPlanarSegments(0.05, 30)                         # list of facet-index lists
m.getCurvaturePerVertex()                             # per-vertex curvature
MeshPart.wireFromMesh(m)                              # boundary wires
MeshPart.projectShapeOnMesh(shape, m, 1.0)            # project a shape onto the mesh
m.trimByPlane(FreeCAD.Vector(0, 0, 5), FreeCAD.Vector(0, 0, 1))
```

`ReverseEngineering` also exposes `approxSurface`, `approxCurve`, `normalEstimation`,
`poissonReconstruction`, `regionGrowingSegmentation`, `sampleConsensus` and
`featureSegmentation`; only `approxSurface` and `normalEstimation` document their arguments
(`help(ReverseEngineering.approxSurface)`). The others are unverified here: test before relying on them.

## Choosing features from the fits

| Fit result | Build |
|---|---|
| Plane facing +/-Z at two levels, bbox in XY | base sketch + Pad (height = distance between planes) |
| Cylinder, axis parallel to Z, radius r, inside the body | Pocket (hole) |
| Cylinder, axis parallel to Z, outside the body | Pad (boss) |
| Cylinder axis along a rotation axis, many coaxial radii | Revolution of a measured profile |
| Repeated identical features at regular spacing | LinearPattern / PolarPattern of one feature |
| Poor / marginal fits, uncovered facets | freeform: say so, approximate, report deviation |

Cylinder `axis` and `point` give the position; snap axes within a degree or two of a world
axis to that axis before building, and snap near-equal radii to one value, because scans are noisy.

## Worked example (runs as-is; replace the stand-in with `mr.load("part.stl")`)

```python
import sys, os
sys.path.insert(0, os.path.expanduser("~/.claude/skills/freecad-scripts/scripts"))
import FreeCAD, Part, Sketcher, MeshPart
import mesh_report as mr
V = FreeCAD.Vector

# stand-in for a scanned part (box + boss + through hole)
src = (Part.makeBox(40, 30, 10).fuse(Part.makeCylinder(8, 20, V(20, 15, 0)))
       .cut(Part.makeCylinder(4, 40, V(20, 15, -5))).removeSplitter())
mesh = MeshPart.meshFromShape(Shape=src, LinearDeflection=0.01, AngularDeflection=0.1)

fits, coverage = mr.fit_primitives(mesh)
cyls = sorted([f for f in fits if f["type"] == "Cylinder"], key=lambda f: f["radius"])
hole, boss = cyls[0], cyls[-1]
bb = mesh.BoundBox
params = dict(BaseLength=bb.XLength, BaseWidth=bb.YLength, BaseHeight=10.0,
              BossRadius=boss["radius"], BossHeight=bb.ZLength - 10.0, HoleRadius=hole["radius"],
              CenterX=boss["point"][0], CenterY=boss["point"][1])

doc = FreeCAD.newDocument("Rebuild")
varset = doc.addObject("App::VarSet", "VarSet")
for name, value in params.items():
    varset.addProperty("App::PropertyLength", name, "Dimensions", name)
    setattr(varset, name, value)
doc.recompute()

body = doc.addObject("PartDesign::Body", "Body")
xy = next(o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane")

def new_sketch(name, z=0.0):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = FreeCAD.Placement(V(0, 0, z), FreeCAD.Rotation())
    return sk

def named(sk, idx, name, expr):
    sk.renameConstraint(idx, name)
    sk.setExpression(f"Constraints.{name}", expr)

# base rectangle
sk = new_sketch("BaseSketch")
pts = [(0, 0), (40, 0), (40, 30), (0, 30)]
for i in range(4):
    a, b = pts[i], pts[(i + 1) % 4]
    sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
for i in range(4):
    sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
for g in (0, 2):
    sk.addConstraint(Sketcher.Constraint("Horizontal", g))
for g in (1, 3):
    sk.addConstraint(Sketcher.Constraint("Vertical", g))
sk.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
named(sk, sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 40.0)), "len", "VarSet.BaseLength")
named(sk, sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 30.0)), "wid", "VarSet.BaseWidth")
pad = body.newObject("PartDesign::Pad", "BasePad")
pad.Profile = sk
pad.setExpression("Length", "VarSet.BaseHeight")

def circle_sketch(name, z, radius_prop):
    s = new_sketch(name, z)
    c = s.addGeometry(Part.Circle(V(20, 15, 0), V(0, 0, 1), 5))
    named(s, s.addConstraint(Sketcher.Constraint("Radius", c, 5.0)), "r", f"VarSet.{radius_prop}")
    named(s, s.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 20.0)), "cx", "VarSet.CenterX")
    named(s, s.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 15.0)), "cy", "VarSet.CenterY")
    return s

boss_pad = body.newObject("PartDesign::Pad", "BossPad")
boss_pad.Profile = circle_sketch("BossSketch", 10.0, "BossRadius")
boss_pad.setExpression("Length", "VarSet.BossHeight")

pocket = body.newObject("PartDesign::Pocket", "HolePocket")
pocket.Profile = circle_sketch("HoleSketch", 30.0, "HoleRadius")
pocket.Type = 1                      # ThroughAll
doc.recompute()

print(body.Shape.Volume, src.Volume)             # 13005.31 13005.31
dev = mr.deviation(mesh, body.Shape, samples=800, tol=0.05)
print(dev["max"], dev["within_tol"])             # ~0.0 1.0

# change a dimension: the model follows
varset.BossRadius = 10
doc.recompute()
```

Measured on 1.1.4: rebuilt volume equals the source volume, all three sketches report
`FullyConstrained == True`, deviation 0, and changing `BossRadius` to 10 mm gives the expected
volume (14136.28).

## Reporting to the user

State: mesh health before/after repair, coverage %, which features were fitted and with what
grade, which regions are freeform or approximate, the deviation figures against the stated
tolerance, and every dimension that was snapped or rounded.
