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
2 end, 3 centre. Name a constraint so an expression can drive it (or address it by position,
`Constraints[1]`, as many existing models do):

```python
idx = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 40.0))
sk.renameConstraint(idx, "len")
sk.setExpression("Constraints.len", "VarSet.BaseLength")
```

Do not name a constraint after a unit symbol. `h`, `m`, `s`, `l`, `t`, `g`, `in`, `mm`, `N` and
`V` all fail with `Failed to parse expression 'Constraints.h'` (verified); `w`, `r`, `a`, `d`,
`len`, `wid`, `cx` are fine. Use descriptive names like `width`.

## VarSet-driven parameters (preferred)

A `App::VarSet` holds the model's dimensions. The user's own models use one object named
`VarSet` with `App::PropertyLength` properties in PascalCase (`BarProfileDiameter`,
`Ring1_2PathDiameter`) and expressions such as `VarSet.Ring1_2PathDiameter + VarSet.BarProfileDiameter`
on sketch constraints. Match that convention.

```python
varset = doc.addObject("App::VarSet", "VarSet")
for name, value in {"BaseLength": 40.0, "BaseHeight": 10.0}.items():
    varset.addProperty("App::PropertyLength", name, "Dimensions", name)   # type, name, group, tooltip
    setattr(varset, name, value)
varset.addProperty("App::PropertyAngle", "Opening", "Dimensions", "Opening angle")
varset.Opening = 30
varset.addProperty("App::PropertyInteger", "Count", "Dimensions", "Number of holes")
varset.Count = 3
doc.recompute()

pad.setExpression("Length", "VarSet.BaseHeight")      # feature property bound to a VarSet property
varset.BaseHeight = 15                                 # change a dimension and recompute
doc.recompute()
```

Derive dependent values with expressions (`VarSet.OuterRadius - VarSet.Wall`) instead of
precomputing them. A Spreadsheet (`Spreadsheet::Sheet`, `sheet.setAlias`, expressions like
`Params.base_len`) also works, but the user prefers VarSets: use a Spreadsheet only if asked.

## More PartDesign features (verified, with expected values)

```python
import math
import FreeCAD, Part, Sketcher
V = FreeCAD.Vector
doc = FreeCAD.newDocument("MoreFeatures")

def new_body(name):
    body = doc.addObject("PartDesign::Body", name)
    return body, {o.Role: o for o in body.Origin.OriginFeatures}

def sketch(body, name, support, sub="", offset=None):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(support, sub)]
    sk.MapMode = "FlatFace"
    if offset:
        sk.AttachmentOffset = offset
    return sk

def rect(sk, w, d, x0=0, y0=0):
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + d), (x0, y0 + d)]
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))

def box_body(name, w=20, d=20, h=10):
    body, o = new_body(name)
    sk = sketch(body, "Base", o["XY_Plane"])
    rect(sk, w, d)
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = sk
    pad.Length = h
    doc.recompute()
    return body, o, pad

def top_edges(pad, z):
    return [f"Edge{i + 1}" for i, e in enumerate(pad.Shape.Edges)
            if all(abs(v.Point.z - z) < 1e-6 for v in e.Vertexes)]

# AdditivePipe: circle profile swept along a straight path sketch (volume pi*r^2*L)
body, o = new_body("Pipe")
path = sketch(body, "Path", o["XZ_Plane"])                    # sketch Y runs along world Z here
path.addGeometry(Part.LineSegment(V(0, 0, 0), V(0, 30, 0)))
prof = sketch(body, "Prof", o["XY_Plane"])
prof.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 3))
pipe = body.newObject("PartDesign::AdditivePipe", "Pipe")
pipe.Profile = prof
pipe.Spine = (path, ["Edge1"])                                # path sketch + the edge to follow
doc.recompute()
print(round(pipe.Shape.Volume, 1), round(math.pi * 9 * 30, 1))          # 848.2 848.2

# Same on a curved path: a quarter-circle arc, volume = pi*r^2 * arc length
body, o = new_body("ArcPipe")
path = sketch(body, "Path", o["XZ_Plane"])
path.addGeometry(Part.ArcOfCircle(Part.Circle(V(20, 0, 0), V(0, 0, 1), 20), math.pi / 2, math.pi))
prof = sketch(body, "Prof", o["XY_Plane"])
prof.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 2))
arc_pipe = body.newObject("PartDesign::AdditivePipe", "Pipe")
arc_pipe.Profile = prof
arc_pipe.Spine = (path, ["Edge1"])
doc.recompute()
print(round(arc_pipe.Shape.Volume, 1), arc_pipe.Shape.isValid())       # 394.8 True

# AdditiveLoft between two sketches (cone frustum: pi*h/3*(R^2 + R*r + r^2))
body, o = new_body("Loft")
s1 = sketch(body, "L1", o["XY_Plane"])
s1.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 10))
s2 = sketch(body, "L2", o["XY_Plane"], offset=FreeCAD.Placement(V(0, 0, 20), FreeCAD.Rotation()))
s2.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5))
loft = body.newObject("PartDesign::AdditiveLoft", "Loft")
loft.Profile = s1
loft.Sections = [s2]
doc.recompute()
print(round(loft.Shape.Volume, 1))                                      # 3665.2

# Chamfer (like Fillet: Base = (feature, [edge names]))
body, o, pad = box_body("Chamfered")
chamfer = body.newObject("PartDesign::Chamfer", "Chamfer")
chamfer.Base = (pad, top_edges(pad, 10))
chamfer.Size = 1
doc.recompute()
print(round(chamfer.Shape.Volume, 2))                                   # 3961.33

# Thickness (hollow out, opening the chosen face)
body, o, pad = box_body("Shell")
top_face = [f"Face{i + 1}" for i, f in enumerate(pad.Shape.Faces)
            if abs(f.CenterOfMass.z - 10) < 1e-6 and f.normalAt(0, 0).z > 0.9]
shell = body.newObject("PartDesign::Thickness", "Thickness")
shell.Base = (pad, top_face)
shell.Value = 2
shell.Mode = 0
shell.Join = 1
doc.recompute()
print(round(shell.Shape.Volume, 1))                                     # 1952.0

# Datum plane, then a sketch on it
body, o, pad = box_body("Datum")
datum = body.newObject("PartDesign::Plane", "DatumPlane")
datum.AttachmentSupport = [(o["XY_Plane"], "")]
datum.MapMode = "FlatFace"
datum.AttachmentOffset = FreeCAD.Placement(V(0, 0, 5), FreeCAD.Rotation())
doc.recompute()
on_datum = sketch(body, "OnDatum", datum)
on_datum.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 3))
doc.recompute()
print(on_datum.Placement.Base.z)                                        # 5.0

# Mirrored about a datum plane through the part (a plane that misses the part does nothing)
body, o, pad = box_body("Mirror")
hole_sk = sketch(body, "HoleSk", o["XY_Plane"], offset=FreeCAD.Placement(V(0, 0, 10), FreeCAD.Rotation()))
hole_sk.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), 2))
pocket = body.newObject("PartDesign::Pocket", "Pocket")
pocket.Profile = hole_sk
pocket.Type = 1                                                         # ThroughAll
mid = body.newObject("PartDesign::Plane", "MidPlane")
mid.AttachmentSupport = [(o["YZ_Plane"], "")]
mid.MapMode = "FlatFace"
mid.AttachmentOffset = FreeCAD.Placement(V(0, 0, 10), FreeCAD.Rotation())   # x = 10
doc.recompute()
mirrored = body.newObject("PartDesign::Mirrored", "Mirrored")
mirrored.Originals = [pocket]
mirrored.MirrorPlane = (mid, [""])
body.Tip = mirrored
doc.recompute()
print(round(body.Shape.Volume, 2), round(4000 - 2 * math.pi * 4 * 10, 2))    # 3748.67 3748.67

# MultiTransform: transformations are separate pattern objects listed in the container
body, o, pad = box_body("Multi")
hole_sk = sketch(body, "HoleSk", o["XY_Plane"], offset=FreeCAD.Placement(V(0, 0, 10), FreeCAD.Rotation()))
hole_sk.addGeometry(Part.Circle(V(3, 3, 0), V(0, 0, 1), 1))
pocket = body.newObject("PartDesign::Pocket", "Pocket")
pocket.Profile = hole_sk
pocket.Type = 1
multi = body.newObject("PartDesign::MultiTransform", "Multi")
multi.Originals = [pocket]
row = body.newObject("PartDesign::LinearPattern", "Row")
row.Direction = (o["X_Axis"], [""])
row.Length = 10
row.Occurrences = 3
multi.Transformations = [row]
body.Tip = multi
doc.recompute()
print(round(body.Shape.Volume, 2), round(4000 - 3 * math.pi * 10, 2))        # 3905.75 3905.75
```

## Multi-body modelling (SubShapeBinder and Boolean)

The user's models are built from several Bodies combined with `SubShapeBinder` and
`PartDesign::Boolean`. A binder brings another Body's shape into the current Body; a Boolean
feature applies Fuse/Cut/Common with another Body.

```python
body_a, oa, pad_a = box_body("BodyA")                                   # 20 x 20 x 10 = 4000
body_b, ob = new_body("BodyB")
sk_b = sketch(body_b, "Base", ob["XY_Plane"])
rect(sk_b, 10, 10, 5, 5)
pad_b = body_b.newObject("PartDesign::Pad", "Pad")
pad_b.Profile = sk_b
pad_b.Length = 20
doc.recompute()

binder = body_a.newObject("PartDesign::SubShapeBinder", "Binder")       # reference only, no cut yet
binder.Support = [(body_b, [""])]
doc.recompute()
print(round(binder.Shape.Volume, 1))                                    # 2000.0 (BodyB's volume)

cut = body_a.newObject("PartDesign::Boolean", "Boolean")
cut.Type = "Cut"                                                         # "Fuse", "Cut", "Common"
cut.addObject(body_b)
doc.recompute()
print(round(body_a.Shape.Volume, 1))                                    # 3000.0 = 4000 - 10*10*10
```

## Sketcher beyond rectangles

```python
body, o = new_body("SketchLab")
sk = sketch(body, "S", o["XY_Plane"])

# construction geometry (second argument True) is not part of the profile
ref = sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)), True)
print(sk.getConstruction(ref))                                           # True

# arc + tangent line: an endpoint-to-endpoint Tangent already implies coincidence,
# so do not add a separate Coincident (it would be redundant)
sk2 = sketch(body, "Tan", o["XY_Plane"])
arc = sk2.addGeometry(Part.ArcOfCircle(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5), 0, math.pi / 2))
line = sk2.addGeometry(Part.LineSegment(V(5, 0, 0), V(5, -10, 0)))
sk2.addConstraint(Sketcher.Constraint("Tangent", arc, 1, line, 1))
sk2.addConstraint(Sketcher.Constraint("Radius", arc, 5.0))
sk2.addConstraint(Sketcher.Constraint("Coincident", arc, 3, -1, 1))      # arc centre on the origin
print(sk2.solve(), sk2.DoF, sk2.RedundantConstraints, sk2.ConflictingConstraints)   # 0 3 [] []

# BSpline through points
sk3 = sketch(body, "Spline", o["XY_Plane"])
spline = Part.BSplineCurve()
spline.interpolate([V(0, 0, 0), V(5, 5, 0), V(10, 0, 0), V(15, 5, 0)])
sk3.addGeometry(spline)
print(sk3.solve())                                                       # 0

# External geometry: reference an edge of another sketch or an origin axis.
# (Referencing a PartDesign feature such as "Pad" raised "not allowed as external geometry".)
base = sketch(body, "BaseRect", o["XY_Plane"])
rect(base, 20, 20)
doc.recompute()                                  # the edge must exist before it can be referenced
sk4 = sketch(body, "UsesExternal", o["XY_Plane"])
sk4.addExternal("BaseRect", "Edge1")
sk4.addExternal(body.Origin.Name, "X_Axis")      # this Body's own origin ("Origin" alone is ambiguous with several Bodies)
line = sk4.addGeometry(Part.LineSegment(V(0, 5, 0), V(10, 5, 0)))
sk4.addConstraint(Sketcher.Constraint("Parallel", line, -3))             # first external edge is -3
print(len(sk4.ExternalGeometry), sk4.solve())                            # 2 0
```

Constraint index `-3` and below address external geometry, in the order it was added.
`sk.solve()` returning a negative number (for example `-2`) means conflicting or redundant
constraints; read `sk.RedundantConstraints` and `sk.ConflictingConstraints` and remove the
duplicate before continuing.

## Common failures

- `PartDesign::Pad ... No object linked` (printed in the console): the feature was created
  with `doc.addObject`; use `body.newObject`.
- A feature stays `Invalid` after `recompute()`: read `feature.State` and the console
  message; usually a sketch is open, self-intersecting, or on the wrong plane.
- Face and edge names (`Face6`, `Edge4`) change when the model changes; compute them from
  geometry (as in the Fillet example) instead of hard-coding after the first build.
- Patterns need `body.Tip = pattern` or later features attach to the pre-pattern shape.
