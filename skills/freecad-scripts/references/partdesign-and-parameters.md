# PartDesign Features and Parametric Control

Everything here was run on FreeCAD 1.1.4. Features must be created with `body.newObject(...)`
inside a `PartDesign::Body`; `doc.addObject("PartDesign::...")` leaves them unlinked.

```python
import math
import FreeCAD, Part, Sketcher
V = FreeCAD.Vector

doc = FreeCAD.newDocument("Features")
body = doc.addObject("PartDesign::Body", "Body")
origin = {o.Role: o for o in body.Origin.OriginFeatures}   # XY_Plane, XZ_Plane, YZ_Plane, X_Axis, ...

def sketch(name, plane="XY_Plane", support=None, sub=""):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(support or origin[plane], sub)]
    sk.MapMode = "FlatFace"
    return sk

# base: closed rectangle -> Pad
s1 = sketch("Base")
pts = [(0, 0), (30, 0), (30, 20), (0, 20)]
for i in range(4):
    a, b = pts[i], pts[(i + 1) % 4]
    s1.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
for i in range(4):
    s1.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = s1
pad.Length = 10
doc.recompute()
print(pad.Shape.Volume)                            # 6000.0
```

## Features

```python
# Hole feature on the top face of the pad (Face6 here; check which face with getSubObject)
hs = sketch("HoleSketch", support=pad, sub="Face6")
hs.addGeometry(Part.Circle(V(15, 10, 0), V(0, 0, 1), 2))
doc.recompute()
hole = body.newObject("PartDesign::Hole", "Hole")
hole.Profile = hs
hole.Diameter = 4
hole.DepthType = "ThroughAll"

# Pocket (cut). Type 1 = ThroughAll; sketch plane is offset to the top face
ps = sketch("PocketSketch")
ps.AttachmentOffset = FreeCAD.Placement(V(0, 0, 10), FreeCAD.Rotation())
ps.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), 1.5))
pocket = body.newObject("PartDesign::Pocket", "Pocket")
pocket.Profile = ps
pocket.Type = 1
doc.recompute()

# Fillet on named edges of the previous feature. Edge names come from the shape:
top_edges = [f"Edge{i + 1}" for i, e in enumerate(body.Shape.Edges)
             if abs(e.Vertexes[0].Point.z - 10) < 1e-6 and abs(e.Vertexes[-1].Point.z - 10) < 1e-6
             and e.Length > 25]
fillet = body.newObject("PartDesign::Fillet", "Fillet")
fillet.Base = (pocket, top_edges[:1])
fillet.Radius = 1
doc.recompute()

# Linear pattern of a feature along the X axis
lp = body.newObject("PartDesign::LinearPattern", "LP")
lp.Originals = [pocket]
lp.Direction = (origin["X_Axis"], [""])
lp.Length = 20
lp.Occurrences = 2
body.Tip = lp                                      # patterns do not become the Tip automatically
doc.recompute()
```

Revolution and PolarPattern (separate document for a clean profile):

```python
d2 = FreeCAD.newDocument("Rev")
b2 = d2.addObject("PartDesign::Body", "B")
role = {o.Role: o for o in b2.Origin.OriginFeatures}
s = b2.newObject("Sketcher::SketchObject", "S")
s.AttachmentSupport = [(role["XZ_Plane"], "")]
s.MapMode = "FlatFace"
for a, c in [((0, 0), (10, 0)), ((10, 0), (10, 20)), ((10, 20), (0, 20)), ((0, 20), (0, 0))]:
    s.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(c[0], c[1], 0)))
for i in range(4):
    s.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
rev = b2.newObject("PartDesign::Revolution", "Rev")
rev.Profile = s
rev.ReferenceAxis = (s, ["V_Axis"])                # the sketch's own vertical axis
rev.Angle = 360
d2.recompute()
print(rev.Shape.Volume, math.pi * 10 ** 2 * 20)    # both 6283.2
```

```python
d3 = FreeCAD.newDocument("Polar")
b3 = d3.addObject("PartDesign::Body", "B")
r3 = {o.Role: o for o in b3.Origin.OriginFeatures}
s = b3.newObject("Sketcher::SketchObject", "S")
s.AttachmentSupport = [(r3["XY_Plane"], "")]
s.MapMode = "FlatFace"
s.addGeometry(Part.Circle(V(10, 0, 0), V(0, 0, 1), 2))
p = b3.newObject("PartDesign::Pad", "P")
p.Profile = s
p.Length = 5
pp = b3.newObject("PartDesign::PolarPattern", "PP")
pp.Originals = [p]
pp.Axis = (r3["Z_Axis"], [""])
pp.Angle = 360
pp.Occurrences = 4
b3.Tip = pp
d3.recompute()
print(b3.Shape.Volume)                             # 251.3 (four 4*pi*5 pegs)
```

Fillets and chamfers inside a sketch: `Sketch.fillet` has a different signature than you
would guess and failed when guessed; use the PartDesign Fillet feature above, or draw the
arc with `Part.ArcOfCircle(Part.Circle(center, normal, radius), start_rad, end_rad)` and
constrain it with `Tangent`.

## Sketch health

```python
sk.solve()                 # 0 means the solver succeeded; it is NOT the degrees of freedom
sk.DoF                     # degrees of freedom left
sk.FullyConstrained        # True when nothing can move
sk.ConflictingConstraints, sk.RedundantConstraints, sk.MalformedConstraints   # lists of indices
```

Check `FullyConstrained` and the three problem lists after building each sketch. A sketch that
recomputes fine but is under-constrained will change shape when a parameter changes. The
`Pad` in the first example above is under-constrained on purpose (`FullyConstrained` is False):
add Horizontal/Vertical, an origin Coincident and two dimensions to fix it.

Constraint index `-1` is the sketch origin / X axis, `-2` the Y axis. Point ids: 1 start,
2 end, 3 centre. Name a constraint so an expression can drive it:

```python
idx = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 40.0))
sk.renameConstraint(idx, "len")
sk.setExpression("Constraints.len", "Params.base_len")
```

## Spreadsheet-driven parameters

```python
sheet = doc.addObject("Spreadsheet::Sheet", "Params")
sheet.Label = "Params"                       # expressions use the label
sheet.set("A1", "base_len"); sheet.set("B1", "40 mm"); sheet.setAlias("B1", "base_len")
doc.recompute()

pad.setExpression("Length", "Params.base_len")       # feature property bound to a cell
sheet.set(sheet.getCellFromAlias("base_len"), "55 mm")   # change by alias, never by cell address
doc.recompute()
```

Give every measured dimension an alias; derive dependent values with expressions
(`Params.outer_r - Params.wall`) instead of precomputing them.

## Common failures

- `PartDesign::Pad ... No object linked` (printed in the console): the feature was created
  with `doc.addObject`; use `body.newObject`.
- A feature stays `Invalid` after `recompute()`: read `feature.State` and the console
  message; usually a sketch is open, self-intersecting, or on the wrong plane.
- Face and edge names (`Face6`, `Edge4`) change when the model changes; compute them from
  geometry (as in the Fillet example) instead of hard-coding after the first build.
- Patterns need `body.Tip = pattern` or later features attach to the pre-pattern shape.
