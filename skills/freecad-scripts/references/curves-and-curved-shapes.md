# Curves and Curved Shapes Workbenches

Two user-installed addons (not part of FreeCAD core), verified on FreeCAD 1.1.4:

| Addon | Version tested | Location |
|---|---|---|
| Curves workbench | 0.6.71 | `~/Library/Application Support/FreeCAD/v1-1/Mod/Curves` |
| Curved Shapes | 1.00.14 | `~/Library/Application Support/FreeCAD/v1-1/Mod/CurvedShapes` |

Their Python APIs are unversioned and can change when the addon updates. Check the version
first (`package.xml` in each folder), and re-test before trusting the examples if it differs.
The Curves README itself calls the workbench experimental.

## Which tool to use

Prefer native PartDesign for anything it can do: `AdditivePipe` along a path, `AdditiveLoft`
between sections, `Revolution`. They are parametric, stay inside a Body and print reliably.
Reach for the addons when you need what core lacks:

| Need | Tool |
|---|---|
| Ribs/sections scaled between bounding curves (wings, hulls, tapered organic shapes) | Curved Shapes `makeCurvedArray` |
| Surface through two rails and several profiles | Curves `Sweep 2 Rails` |
| Surface skinning a grid of curves | Curves `Gordon` |
| Smooth ruled surface between two edges | Curves `HQ Ruled Surface` |
| Join several edges into one smooth BSpline | Curves `JoinCurve` |

Results are Part-level shells/faces, not PartDesign features. To use one inside a Body, bring
it in with a `PartDesign::SubShapeBinder` (see the multi-body section of
`partdesign-and-parameters.md`) or work at Part level. Surfaces only become solids if you
close them (`Part.Shell` -> `Part.Solid`) or ask Curved Shapes for `Solid=True`; check
`shape.isValid()` and `shape.Volume` before relying on one for printing.

## Availability: headless vs GUI

- `import CurvedShapes` works in `freecadcmd` and in the GUI. Its `make*` functions run headless.
- Curves library modules without GUI commands import headless (`freecad.Curves.nurbs_tools`,
  `gordon`, `blend_curve`, `curves_to_surface`). The feature modules (`Sweep2RailsFP`,
  `JoinCurves`, `HQRuledSurfaceFP`, `gordonFP`, ...) call `FreeCADGui.addCommand` on import and
  therefore need the GUI session: run them through the MCP `execute_code` tool, not `freecadcmd`.
- Both addons' folders are on `sys.path` in the 1.1 user profile, so no path setup is needed.

## Curved Shapes (verified headless)

All input shapes must be document objects with a `.Shape` (`Part::Feature`, sketch, Draft
object). The functions add a `Part::FeaturePython` object and recompute.

```python
import FreeCAD, Part
import CurvedShapes
V = FreeCAD.Vector
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("CS")

def feat(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o

# a circular rib at x=0 and two straight hull curves that diverge in Z along X
rib = feat("Rib", Part.Wire(Part.makeCircle(10, V(0, 0, 0), V(1, 0, 0))))
top = feat("HullTop", Part.makeLine((0, 0, 10), (100, 0, 30)))
bottom = feat("HullBottom", Part.makeLine((0, 0, -10), (100, 0, -30)))
doc.recompute()

arr = CurvedShapes.makeCurvedArray(Base=rib, Hullcurves=[top, bottom],
                                   Axis=V(1, 0, 0), Items=6, Solid=True)
print(arr.Shape.ShapeType, arr.Shape.isValid(), round(arr.Shape.Volume))   # Solid True 62758

arr.Items = 8                       # properties stay editable; recompute rebuilds
doc.recompute()
```

Rules that matter (the first one cost a wrong result in testing):

- **`Axis` is a direction mask, not a length.** Use a unit-ish vector such as `V(1,0,0)`. The
  code multiplies it with the hull curves' bounding box, so `V(100,0,0)` pushes every rib far
  outside the hull and the result is empty (zero faces, zero volume) with no error.
- Ribs are scaled only along the coordinate axes in which the hull curves actually extend. In
  the example the hulls vary in Z only, so the circle becomes an ellipse growing in Z while Y
  stays 10: volume is about pi * 10 * (area under the Z half-width) = 62,832, and the tool
  returned 62,758 (loft approximation).
- `Items=n` with neither `Surface` nor `Solid` returns just the ribs (n wires). `Surface=True`
  lofts a face, `Solid=True` lofts a solid. `Positions=[0.0 ... 1.0]` places ribs explicitly and
  overrides `Items`. `Twist` / `Twists` rotate ribs about the axis.
- Other constructors exist and ran without error on simple inputs, but their geometry was not
  checked: `makeCurvedSegment(Shape1=, Shape2=, Hullcurves=[], Items=, Surface=)`,
  `makeInterpolatedMiddle(Shape1=, Shape2=)`, `makeCurvedPathArray(Base=, Path=, Hullcurves=[])`,
  `cutSurfaces`, `makeNotchConnector`. Verify the result's area/volume/validity yourself.

## Curves workbench (GUI session only)

The feature classes follow one pattern: a `...Command` class with a `make...Feature` method
that builds a `Part::FeaturePython` from the objects you pass. Call that method directly
instead of simulating a selection. The created object's `Name`/`Label` have spaces replaced by
underscores (`Sweep_2_Rails`), so take the object from `doc.Objects[-1]` rather than looking it
up by the menu label. The tools print debug lines to the console; that is normal.

```python
import FreeCAD as App
import Part
V = App.Vector
doc = App.newDocument("CurvesDemo")

def feat(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o

def bspline(points):
    c = Part.BSplineCurve()
    c.interpolate(points)
    return c.toShape()

# Sweep 2 Rails: first two objects are the rails, the rest are profiles
from freecad.Curves import Sweep2RailsFP
r1 = feat("Rail1", bspline([V(0, 0, 0), V(2, 0, 25), V(0, 0, 50)]))
r2 = feat("Rail2", bspline([V(20, 0, 0), V(24, 0, 25), V(20, 0, 50)]))
p1 = feat("Prof1", Part.makeLine((0, 0, 0), (20, 0, 0)))
p2 = feat("Prof2", Part.makeLine((0, 0, 50), (20, 0, 50)))
doc.recompute()
Sweep2RailsFP.Sweep2RailsCommand().makeFeature([r1, r2, p1, p2])
sweep = doc.Objects[-1]
print(sweep.State, round(sweep.Shape.Area, 1))      # ['Up-to-date'] 1066.7 (1000.0 on straight rails)

# JoinCurve: one smooth BSpline from connected edges, given as (object, ("EdgeN",)) pairs
from freecad.Curves import JoinCurves
a = feat("LA", Part.makeLine((0, 0, 0), (10, 0, 0)))
b = feat("LB", Part.makeLine((10, 0, 0), (10, 10, 0)))
doc.recompute()
JoinCurves.joinCommand().makeJoinFeature([(a, ("Edge1",)), (b, ("Edge1",))])
print(doc.Objects[-1].Shape.Length)                  # 20.0, one edge

# HQ Ruled Surface between two curves
from freecad.Curves import HQRuledSurfaceFP
c1 = feat("HA", Part.makeLine((0, 0, 0), (10, 0, 0)))
c2 = feat("HB", Part.makeLine((0, 10, 0), (10, 10, 0)))
doc.recompute()
HQRuledSurfaceFP.HQ_Ruled_Surface_Command().makeFeature([c1, c2])
print(round(doc.Objects[-1].Shape.Area, 2))          # 100.01

# Gordon surface: a network of curves crossing each other
from freecad.Curves import gordonFP
u1 = feat("U1", bspline([V(0, 0, 0), V(5, 0, 0), V(10, 0, 0)]))
u2 = feat("U2", bspline([V(0, 10, 0), V(5, 10, 0), V(10, 10, 0)]))
v1 = feat("V1", bspline([V(0, 0, 0), V(0, 5, 0), V(0, 10, 0)]))
v2 = feat("V2", bspline([V(10, 0, 0), V(10, 5, 0), V(10, 10, 0)]))
doc.recompute()
gordonFP.gordonCommand().makeGordonFeature([u1, u2, v1, v2])
gordon = doc.Objects[-1]
print(round(gordon.Shape.Area, 1))                   # 100.0
```

Measured: Sweep 2 Rails 1000.0 on straight rails and 1066.7 on bulged rails; JoinCurve length
20.0; HQ Ruled Surface 100.01; Gordon 100.0, and after moving three of its input curves it
recomputed to 200.0, so these features stay parametric with respect to their inputs.

Not verified (do not present these as working): `PipeShell` (needs `pipeshellProfile`
objects and an `(object, ("EdgeN",))` spine; its default output is "Sections", not a
surface), `blend_curve.BlendCurve` / `BlendSurface` from the library, `IsoCurve`,
`CurveOnSurface`, `approximate`, and the other tools in `Curves/freecad/Curves`.
Look at the `...Command.makeFeature` of a tool in that folder to learn its input convention,
then test with a case whose answer you can compute.

## Reverse engineering with these tools

For freeform regions that primitive fitting cannot explain (see
`mesh-reverse-engineering.md`), Gordon or Sweep 2 Rails over curves traced from mesh
cross-sections (`Mesh.crossSections` -> `Part.BSplineCurve.interpolate`) can rebuild the
surface; measure its deviation with `mesh_report.deviation` and report it. This pipeline was
not run end to end here.
