---
name: freecad-scripts
description: 'Use when writing or debugging FreeCAD 1.1 Python: scripts, macros, or code sent through the freecad MCP execute_code tools. Also use when reverse engineering an STL/OBJ/3MF mesh into a parametric model, building a CAD model that matches a photo, drawing or screenshot, driving PartDesign and Sketcher dimensions from a VarSet, building Assembly joints, exporting 3MF for 3D printing, or using the Curves and Curved Shapes workbenches. Covers Part, PartDesign, Sketcher, Assembly, Mesh, Draft, FEM, FeaturePython objects, PySide6 task panels, Coin3D/Pivy, and workbenches. Check the deprecated-API table before using any older example.'
---

# FreeCAD Scripts

Expert skill for generating production-quality Python scripts for the FreeCAD CAD application. Interprets shorthand, quasi-code, and natural language descriptions of 3D modeling tasks and translates them into correct FreeCAD Python API calls.

## When to Use This Skill

- Writing Python scripts for FreeCAD's built-in console or macro system
- Creating or manipulating 3D geometry (Part, PartDesign, Mesh, Sketcher, Assembly, FEM)
- Building parametric FeaturePython objects with custom properties
- Developing GUI tools using PySide/Qt within FreeCAD
- Manipulating the Coin3D scenegraph via Pivy
- Creating custom workbenches or Gui Commands
- Automating repetitive CAD operations with macros
- Converting between mesh and solid representations
- Scripting FEM analyses

## Prerequisites

- FreeCAD 1.1.x (verified against 1.1.4); Python 3.11 and Qt6/PySide6 are bundled
- For GUI work: `from PySide import QtWidgets, QtCore, QtGui` (FreeCAD's shim; resolves to PySide6). `PySide2` no longer exists
- For scenegraph: Pivy (bundled with FreeCAD)
- Headless runs: `freecadcmd script.py` (macOS: `/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd`)

## Start With the Right Workflow

Match the request before writing code. These are workflows, not API lookups; read the file first.

| Request | Read first |
|---|---|
| "Reverse engineer this mesh/STL", "make this scan parametric", "fit a model to this mesh" | [mesh-reverse-engineering.md](references/mesh-reverse-engineering.md) |
| "Model this from a photo/drawing/screenshot", "match this image" | [images-to-cad.md](references/images-to-cad.md) |
| Parametric parts, Pocket/Hole/Fillet/patterns, VarSet-driven dimensions | [partdesign-and-parameters.md](references/partdesign-and-parameters.md) |
| Assemblies, joints, mating parts, exporting 3MF / preparing for 3D printing | [assembly-and-3mf.md](references/assembly-and-3mf.md) |
| Curves workbench, Curved Shapes, NURBS surfaces, sweeps along rails, lofted/curved arrays | [curves-and-curved-shapes.md](references/curves-and-curved-shapes.md) |

Rules that apply to all three:
- Build parametric models in a `PartDesign::Body` with dimensions in an `App::VarSet` (the user's convention: one object named `VarSet`, `App::PropertyLength` properties in PascalCase), never a faceted mesh-to-solid conversion or hard-coded numbers. Do not use a Spreadsheet unless asked.
- Prefer native PartDesign and Sketcher features; use the Curves / Curved Shapes addons only for what core lacks, and verify addon output (it is Part-level, not a PartDesign feature).
- Model each assembly part as its own Body; the user exports 3MF for 3D printing, so default to millimetres and verify exported meshes are closed solids.
- Establish scale and units before measuring anything; ask for one real dimension if there is none.
- After building, compare against the source (deviation for meshes, a rendered view for images) and report the numbers, including what was approximated or assumed.
- Test unfamiliar calls headless first (`execute_code_headless` or `freecadcmd`), then run in the GUI.

## Deprecated or Removed APIs (FreeCAD 1.1)

Check this table before writing code from memory or from older examples.

| Do not use | Use instead (verified in 1.1.4) |
|---|---|
| `from PySide2 import ...` | `from PySide import ...` (shim) or `PySide6` |
| `dialog.exec_()` | `dialog.exec()` |
| `getStandardButtons` returning `int(A \| B)` | return the flag: `SB.Ok \| SB.Cancel` |
| `import FEM` | `import Fem`, `import ObjectsFem` |
| `ObjectsFem.makeSolverCalculixCcxTools` | `ObjectsFem.makeSolverCalculiXCcxTools` or `makeSolverCalculiX` |
| Gmsh `mesh.Part = obj` | `mesh.Shape = obj` |
| `import Drawing` | `import TechDraw` |
| `importOBJ` module | `Mesh.export([obj], "x.obj")` |
| `sketch.Support = ...` | `sketch.AttachmentSupport = [(plane, "")]` with `sketch.MapMode = "FlatFace"` |
| `Sketcher.Constraint("Fixed", ...)` | `Block` (lock geometry) or a Coincident constraint to the origin `(-1, 1)` |
| `Draft.makeArray(...)` | `Draft.make_ortho_array`, `make_polar_array`, `make_circular_array` |
| Draft camelCase (`makeLine`, `makeCircle`, ...; legacy aliases) | snake_case (`make_line`, `make_circle`, ...) |
| `PartDesign::Pad` via `doc.addObject` | `body.newObject("PartDesign::Pad", ...)` inside a `PartDesign::Body` |
| `ViewObject.DiffuseColor` | `ViewObject.ShapeAppearance` (list of `FreeCAD.Material`) and `ViewObject.Transparency` |
| `:/icons/Part_Box.svg` (null icon) | `:/icons/freecad.svg` or a file path |
| `Std_Macro` command | `Std_DlgMacroExecute` |
| Raytracing, Drawing workbenches | removed from core |

The `Path` module still imports as `import Path`; the workbench is now called CAM.

### Using the freecad MCP server

- `execute_code` runs in the live GUI. Do not call a modal `dialog.exec()` there (it blocks the GUI thread); use task panels.
- `FreeCAD.GuiUp` is true there, so `ViewObject` is available; under `freecadcmd` it is `None`. Guard with `if FreeCAD.GuiUp:`.
- Prefer `execute_code_headless` / `freecadcmd` for pure geometry; test unfamiliar calls there first.

## FreeCAD Python Environment

FreeCAD embeds a Python interpreter. Scripts run in an environment where these key modules are available:

```python
import FreeCAD          # Core module (also aliased as 'App')
import FreeCADGui       # GUI module (also aliased as 'Gui') — only in GUI mode
import Part             # Part workbench — BRep/OpenCASCADE shapes
import Mesh             # Mesh workbench — triangulated meshes
import Sketcher         # Sketcher workbench — 2D constrained sketches
import Draft            # Draft workbench — 2D drawing tools
import Arch             # Arch/BIM workbench
import Path             # CAM workbench (module name is still Path)
import Fem              # FEM workbench (ObjectsFem for creating objects)
import TechDraw         # TechDraw workbench (replaces Drawing)
import BOPTools         # Boolean operations
import CompoundTools    # Compound shape utilities
```

### The FreeCAD Document Model

```python
# Create or access a document
doc = FreeCAD.newDocument("MyDoc")
doc = FreeCAD.ActiveDocument

# Add objects
box = doc.addObject("Part::Box", "MyBox")
box.Length = 10.0
box.Width = 10.0
box.Height = 10.0

# Recompute
doc.recompute()

# Access objects
obj = doc.getObject("MyBox")
obj = doc.MyBox  # Attribute access also works

# Remove objects
doc.removeObject("MyBox")
```

## Core Concepts

### Vectors and Placements

```python
import FreeCAD

# Vectors
v1 = FreeCAD.Vector(1, 0, 0)
v2 = FreeCAD.Vector(0, 1, 0)
v3 = v1.cross(v2)          # Cross product
d = v1.dot(v2)              # Dot product
v4 = v1 + v2                # Addition
length = v1.Length           # Magnitude
v_norm = FreeCAD.Vector(v1)
v_norm.normalize()           # In-place normalize

# Rotations
rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 45)  # axis, angle(deg)
rot = FreeCAD.Rotation(0, 0, 45)                       # Euler angles (yaw, pitch, roll)

# Placements (position + orientation)
placement = FreeCAD.Placement(
    FreeCAD.Vector(10, 20, 0),    # translation
    FreeCAD.Rotation(0, 0, 45),   # rotation
    FreeCAD.Vector(0, 0, 0)       # center of rotation
)
obj.Placement = placement

# Matrix (4x4 transformation)
import math
mat = FreeCAD.Matrix()
mat.move(FreeCAD.Vector(10, 0, 0))
mat.rotateZ(math.radians(45))
```

### Creating and Manipulating Geometry (Part Module)

The Part module wraps OpenCASCADE and provides BRep solid modeling:

```python
import FreeCAD
import Part

# --- Primitive Shapes ---
box = Part.makeBox(10, 10, 10)               # length, width, height
cyl = Part.makeCylinder(5, 20)               # radius, height
sphere = Part.makeSphere(10)                  # radius
cone = Part.makeCone(5, 2, 10)               # r1, r2, height
torus = Part.makeTorus(10, 2)                 # major_r, minor_r

# --- Wires and Edges ---
edge1 = Part.makeLine((0, 0, 0), (10, 0, 0))
edge2 = Part.makeLine((10, 0, 0), (10, 10, 0))
edge3 = Part.makeLine((10, 10, 0), (0, 0, 0))
wire = Part.Wire([edge1, edge2, edge3])

# Circles and arcs
circle = Part.makeCircle(5)                   # radius
arc = Part.makeCircle(5, FreeCAD.Vector(0, 0, 0),
                       FreeCAD.Vector(0, 0, 1), 0, 180)  # start/end angle

# --- Faces ---
face = Part.Face(wire)                        # From a closed wire

# --- Solids from Faces/Wires ---
extrusion = face.extrude(FreeCAD.Vector(0, 0, 10))       # Extrude
revolved = face.revolve(FreeCAD.Vector(0, 0, 0),
                         FreeCAD.Vector(0, 0, 1), 360)    # Revolve

# --- Boolean Operations ---
fused = box.fuse(cyl)           # Union
cut = box.cut(cyl)              # Subtraction
common = box.common(cyl)        # Intersection
fused_clean = fused.removeSplitter()  # Clean up seams

# --- Fillets and Chamfers ---
filleted = box.makeFillet(1.0, box.Edges)          # radius, edges
chamfered = box.makeChamfer(1.0, box.Edges)        # dist, edges

# --- Loft and Sweep ---
loft = Part.makeLoft([wire1, wire2], True)          # wires, solid
swept = Part.Wire([path_edge]).makePipeShell([profile_wire],
                                              True, False)  # solid, frenet

# --- BSpline Curves ---
from FreeCAD import Vector
points = [Vector(0,0,0), Vector(1,2,0), Vector(3,1,0), Vector(4,3,0)]
bspline = Part.BSplineCurve()
bspline.interpolate(points)
edge = bspline.toShape()

# --- Show in document ---
Part.show(box, "MyBox")    # Quick display (adds to active doc)
# Or explicitly:
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()
obj = doc.addObject("Part::Feature", "MyShape")
obj.Shape = box
doc.recompute()
```

### Topological Exploration

```python
shape = obj.Shape

# Access sub-elements
shape.Vertexes    # List of Vertex objects
shape.Edges       # List of Edge objects
shape.Wires       # List of Wire objects
shape.Faces       # List of Face objects
shape.Shells      # List of Shell objects
shape.Solids      # List of Solid objects

# Bounding box
bb = shape.BoundBox
print(bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)
print(bb.Center)

# Properties
shape.Volume
shape.Area
shape.Length       # For edges/wires
face.Surface       # Underlying geometric surface
edge.Curve         # Underlying geometric curve

# Shape type
shape.ShapeType    # "Solid", "Shell", "Face", "Wire", "Edge", "Vertex", "Compound"
```

### Mesh Module

```python
import Mesh

# Create mesh from vertices and facets
mesh = Mesh.Mesh()
mesh.addFacet(
    0.0, 0.0, 0.0,   # vertex 1
    1.0, 0.0, 0.0,   # vertex 2
    0.0, 1.0, 0.0    # vertex 3
)

# Import/Export
mesh = Mesh.Mesh("/path/to/file.stl")
mesh.write("/path/to/output.stl")

# Convert Part shape to Mesh
import Part
import MeshPart
shape = Part.makeBox(1, 1, 1)
mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.1,
                                AngularDeflection=0.5)

# Convert Mesh to Part shape
shape = Part.Shape()
shape.makeShapeFromMesh(mesh.Topology, 0.05)  # tolerance
solid = Part.makeSolid(shape)                  # valid only for a closed, watertight mesh
```

### Sketcher Module

```python
import Sketcher

# Standalone sketch (placed via Placement) -- for PartDesign use body.newObject, see Common Patterns
sketch = doc.addObject("Sketcher::SketchObject", "MySketch")
sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation())

# Add geometry (returns geometry index)
idx_line = sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)))
idx_circle = sketch.addGeometry(Part.Circle(
    FreeCAD.Vector(5, 5, 0), FreeCAD.Vector(0, 0, 1), 3))

# Add constraints
sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 3, 0, 2))   # circle center (pt 3) on line end (pt 2)
sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10.0))
sketch.addConstraint(Sketcher.Constraint("Radius", 1, 3.0))
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))  # pin start point to origin
# sketch.addConstraint(Sketcher.Constraint("Block", 0))               # lock a whole geometry
# Constraint types: Coincident, Horizontal, Vertical, Parallel, Perpendicular,
#   Tangent, Equal, Symmetric, Distance, DistanceX, DistanceY, Radius, Diameter,
#   Angle, Block, InternalAlignment. There is no "Fixed" type.

doc.recompute()
```

### Draft Module

```python
import Draft
import FreeCAD

# 2D shapes (snake_case API; camelCase names are legacy aliases)
line = Draft.make_line(FreeCAD.Vector(0,0,0), FreeCAD.Vector(10,0,0))
circle = Draft.make_circle(5)
rect = Draft.make_rectangle(10, 5)
poly = Draft.make_polygon(6, radius=5)   # hexagon

# Operations
moved = Draft.move(obj, FreeCAD.Vector(10, 0, 0), copy=True)
rotated = Draft.rotate(obj, 45, FreeCAD.Vector(0,0,0),
                        axis=FreeCAD.Vector(0,0,1), copy=True)
scaled = Draft.scale(obj, FreeCAD.Vector(2,2,2), center=FreeCAD.Vector(0,0,0),
                      copy=True)
offset = Draft.offset(wire_obj, FreeCAD.Vector(1,0,0))   # wire_obj must be a 2D object that has been recomputed
array = Draft.make_ortho_array(obj, FreeCAD.Vector(15,0,0),
                               FreeCAD.Vector(0,15,0), FreeCAD.Vector(0,0,15),
                               3, 3, 1)   # xvec, yvec, zvec, nx, ny, nz
```

## Creating Parametric Objects (FeaturePython)

FeaturePython objects are custom parametric objects with properties that trigger recomputation:

```python
import FreeCAD
import Part

class MyBox:
    """A custom parametric box."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLength", "Length", "Dimensions",
                         "Box length").Length = 10.0
        obj.addProperty("App::PropertyLength", "Width", "Dimensions",
                         "Box width").Width = 10.0
        obj.addProperty("App::PropertyLength", "Height", "Dimensions",
                         "Box height").Height = 10.0

    def execute(self, obj):
        """Called on document recompute."""
        obj.Shape = Part.makeBox(obj.Length, obj.Width, obj.Height)

    def onChanged(self, obj, prop):
        """Called when a property changes."""
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class ViewProviderMyBox:
    """View provider for custom icon and display settings."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ":/icons/freecad.svg"

    def attach(self, vobj):
        self.Object = vobj.Object

    def updateData(self, obj, prop):
        pass

    def onChanged(self, vobj, prop):
        pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


# --- Usage ---
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Test")
obj = doc.addObject("Part::FeaturePython", "CustomBox")
MyBox(obj)
if FreeCAD.GuiUp:
    ViewProviderMyBox(obj.ViewObject)   # ViewObject is None under freecadcmd
doc.recompute()
```

### Common Property Types

| Property Type | Python Type | Description |
|---|---|---|
| `App::PropertyBool` | `bool` | Boolean |
| `App::PropertyInteger` | `int` | Integer |
| `App::PropertyFloat` | `float` | Float |
| `App::PropertyString` | `str` | String |
| `App::PropertyLength` | `float` (units) | Length with units |
| `App::PropertyAngle` | `float` (deg) | Angle in degrees |
| `App::PropertyVector` | `FreeCAD.Vector` | 3D vector |
| `App::PropertyPlacement` | `FreeCAD.Placement` | Position + rotation |
| `App::PropertyLink` | object ref | Link to another object |
| `App::PropertyLinkList` | list of refs | Links to multiple objects |
| `App::PropertyEnumeration` | `list`/`str` | Dropdown selection |
| `App::PropertyFile` | `str` | File path |
| `App::PropertyColor` | `tuple` | RGB color (0.0-1.0) |
| `App::PropertyPythonObject` | any | Serializable Python object |

## Creating GUI Tools

### Gui Commands

```python
import FreeCAD
import FreeCADGui

class MyCommand:
    """A custom toolbar/menu command."""

    def GetResources(self):
        return {
            "Pixmap": ":/icons/freecad.svg",
            "MenuText": "My Custom Command",
            "ToolTip": "Creates a custom box",
            "Accel": "Ctrl+Shift+B"
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        # Command logic here
        FreeCAD.Console.PrintMessage("Command activated\n")

FreeCADGui.addCommand("My_CustomCommand", MyCommand())
```

### PySide Dialogs

```python
from PySide import QtWidgets, QtCore, QtGui

class MyDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or FreeCADGui.getMainWindow())
        self.setWindowTitle("My Tool")
        self.setMinimumWidth(300)

        layout = QtWidgets.QVBoxLayout(self)

        # Input fields
        self.label = QtWidgets.QLabel("Length:")
        self.spinbox = QtWidgets.QDoubleSpinBox()
        self.spinbox.setRange(0.1, 1000.0)
        self.spinbox.setValue(10.0)
        self.spinbox.setSuffix(" mm")

        form = QtWidgets.QFormLayout()
        form.addRow(self.label, self.spinbox)
        layout.addLayout(form)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_ok = QtWidgets.QPushButton("OK")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

# Usage
dialog = MyDialog()
if dialog.exec() == QtWidgets.QDialog.Accepted:
    length = dialog.spinbox.value()
    FreeCAD.Console.PrintMessage(f"Length: {length}\n")
```

### Task Panel (Recommended for FreeCAD integration)

```python
import FreeCAD
import FreeCADGui
from PySide import QtWidgets

class MyTaskPanel:
    """Task panel shown in the left sidebar."""

    def __init__(self):
        self.form = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self.form)
        self.spinbox = QtWidgets.QDoubleSpinBox()
        self.spinbox.setValue(10.0)
        layout.addWidget(QtWidgets.QLabel("Length:"))
        layout.addWidget(self.spinbox)

    def accept(self):
        # Called when user clicks OK
        length = self.spinbox.value()
        FreeCAD.Console.PrintMessage(f"Accepted: {length}\n")
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        FreeCADGui.Control.closeDialog()
        return True

    def getStandardButtons(self):
        SB = QtWidgets.QDialogButtonBox.StandardButton
        return SB.Ok | SB.Cancel   # return the flag itself; int() fails in PySide6

# Show the panel
panel = MyTaskPanel()
FreeCADGui.Control.showDialog(panel)
```

## Coin3D Scenegraph (Pivy)

```python
from pivy import coin
import FreeCADGui

# Access the scenegraph root
sg = FreeCADGui.ActiveDocument.ActiveView.getSceneGraph()

# Add a custom separator with a sphere
sep = coin.SoSeparator()
mat = coin.SoMaterial()
mat.diffuseColor.setValue(1.0, 0.0, 0.0)  # Red
trans = coin.SoTranslation()
trans.translation.setValue(10, 10, 10)
sphere = coin.SoSphere()
sphere.radius.setValue(2.0)
sep.addChild(mat)
sep.addChild(trans)
sep.addChild(sphere)
sg.addChild(sep)

# Remove later
sg.removeChild(sep)
```

## Custom Workbench Creation

```python
import FreeCADGui

class MyWorkbench(FreeCADGui.Workbench):
    MenuText = "My Workbench"
    ToolTip = "A custom workbench"
    Icon = ":/icons/freecad.svg"

    def Initialize(self):
        """Called at workbench activation."""
        import MyCommands  # Import your command module
        self.appendToolbar("My Tools", ["My_CustomCommand"])
        self.appendMenu("My Menu", ["My_CustomCommand"])

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(MyWorkbench)
```

## Macro Best Practices

```python
# Standard macro header
# -*- coding: utf-8 -*-
# FreeCAD Macro: MyMacro
# Description: Brief description of what the macro does
# Author: YourName
# Version: 1.0
# Date: 2026-04-07

import FreeCAD
import Part
from FreeCAD import Base

# Guard for GUI availability
if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtWidgets, QtCore

def main():
    doc = FreeCAD.ActiveDocument
    if doc is None:
        FreeCAD.Console.PrintError("No active document\n")
        return

    if FreeCAD.GuiUp:
        sel = FreeCADGui.Selection.getSelection()
        if not sel:
            FreeCAD.Console.PrintWarning("No objects selected\n")

    # ... macro logic ...

    doc.recompute()
    FreeCAD.Console.PrintMessage("Macro completed\n")

if __name__ == "__main__":
    main()
```

### Selection Handling

```python
import FreeCADGui

# Get selected objects
sel = FreeCADGui.Selection.getSelection()           # List of objects
sel_ex = FreeCADGui.Selection.getSelectionEx()       # Extended (sub-elements)

for selobj in sel_ex:
    obj = selobj.Object
    for sub in selobj.SubElementNames:
        print(f"{obj.Name}.{sub}")
        shape = obj.getSubObject(sub)  # Get sub-shape

# Select programmatically
FreeCADGui.Selection.addSelection(doc.MyBox)
FreeCADGui.Selection.addSelection(doc.MyBox, "Face1")
FreeCADGui.Selection.clearSelection()
```

### Console Output

```python
FreeCAD.Console.PrintMessage("Info message\n")
FreeCAD.Console.PrintWarning("Warning message\n")
FreeCAD.Console.PrintError("Error message\n")
FreeCAD.Console.PrintLog("Debug/log message\n")
```

## Common Patterns

### Parametric Pad from Sketch (PartDesign)

```python
import FreeCAD, Part, Sketcher
V = FreeCAD.Vector
doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Pad")

body = doc.addObject("PartDesign::Body", "Body")
xy = next(o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane")

sketch = body.newObject("Sketcher::SketchObject", "Sketch")
sketch.AttachmentSupport = [(xy, "")]
sketch.MapMode = "FlatFace"

pts = [(0, 0), (10, 0), (10, 10), (0, 10)]
for i in range(4):
    a, b = pts[i], pts[(i + 1) % 4]
    sketch.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
for i in range(4):
    sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))
sketch.addConstraint(Sketcher.Constraint("Vertical", 1))
sketch.addConstraint(Sketcher.Constraint("Vertical", 3))
sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10.0))
sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10.0))
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))  # corner at origin

pad = body.newObject("PartDesign::Pad", "Pad")   # must live in a Body
pad.Profile = sketch
pad.Length = 5.0
doc.recompute()
print(pad.Shape.Volume, pad.State)   # 500.0 ['Up-to-date']
```

### Export Shapes

```python
# STEP export
Part.export([doc.MyBox], "/path/to/output.step")

# STL export (mesh)
import Mesh
Mesh.export([doc.MyBox], "/path/to/output.stl")

# IGES export
Part.export([doc.MyBox], "/path/to/output.iges")

# OBJ (via Mesh; the importOBJ module no longer exists)
Mesh.export([doc.MyBox], "/path/to/output.obj")
```

### Units and Quantities

```python
# FreeCAD uses mm internally
q = FreeCAD.Units.Quantity("10 mm")
q_inch = FreeCAD.Units.Quantity("1 in")
print(q_inch.getValueAs("mm"))  # 25.4

# Parse user input with units
q = FreeCAD.Units.parseQuantity("2.5 in")
value_mm = float(q)  # Value in mm (internal unit)
```

## Compensation Rules (Quasi-Coder Integration)

When interpreting shorthand or quasi-code for FreeCAD scripts:

1. **Terminology mapping**: "box" → `Part.makeBox()`, "cylinder" → `Part.makeCylinder()`, "sphere" → `Part.makeSphere()`, "merge/combine/join" → `.fuse()`, "subtract/cut/remove" → `.cut()`, "intersect" → `.common()`, "round edges/fillet" → `.makeFillet()`, "bevel/chamfer" → `.makeChamfer()`
2. **Implicit document**: If no document handling is mentioned, wrap in standard `doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()`
3. **Units assumption**: Default to millimeters unless stated otherwise
4. **Recompute**: Always call `doc.recompute()` after modifications
5. **GUI guard**: Wrap GUI-dependent code in `if FreeCAD.GuiUp:` when the script may run headless
6. **Part.show()**: Use `Part.show(shape, "Name")` for quick display, or `doc.addObject("Part::Feature", "Name")` for named persistent objects

## References

### Primary Links

- [Writing Python code](https://wiki.freecad.org/Manual:A_gentle_introduction#Writing_Python_code)
- [Manipulating FreeCAD objects](https://wiki.freecad.org/Manual:A_gentle_introduction#Manipulating_FreeCAD_objects)
- [Vectors and Placements](https://wiki.freecad.org/Manual:A_gentle_introduction#Vectors_and_Placements)
- [Creating and manipulating geometry](https://wiki.freecad.org/Manual:Creating_and_manipulating_geometry)
- [Creating parametric objects](https://wiki.freecad.org/Manual:Creating_parametric_objects)
- [Creating interface tools](https://wiki.freecad.org/Manual:Creating_interface_tools)
- [Python](https://en.wikipedia.org/wiki/Python_%28programming_language%29)
- [Introduction to Python](https://wiki.freecad.org/Introduction_to_Python)
- [Python scripting tutorial](https://wiki.freecad.org/Python_scripting_tutorial)
- [FreeCAD scripting basics](https://wiki.freecad.org/FreeCAD_Scripting_Basics)
- [Gui Command](https://wiki.freecad.org/Gui_Command)

### Bundled Reference Documents

See the [references/](references/) directory for topic-organized guides:

1. [scripting-fundamentals.md](references/scripting-fundamentals.md) — Core scripting, document model, console
2. [geometry-and-shapes.md](references/geometry-and-shapes.md) — Part, Mesh, Sketcher, topology
3. [parametric-objects.md](references/parametric-objects.md) — FeaturePython, properties, scripted objects
4. [gui-and-interface.md](references/gui-and-interface.md) — PySide, dialogs, task panels, Coin3D
5. [workbenches-and-advanced.md](references/workbenches-and-advanced.md) — Workbenches, macros, FEM, CAM, recipes
6. [mesh-reverse-engineering.md](references/mesh-reverse-engineering.md) — Mesh triage, repair, primitive fitting, parametric rebuild, deviation
7. [images-to-cad.md](references/images-to-cad.md) — Scale from images, pixel measurement, build-compare loop
8. [partdesign-and-parameters.md](references/partdesign-and-parameters.md) — PartDesign features (pipes, lofts, patterns, multi-body Boolean), Sketcher, sketch health, VarSet parameters
9. [assembly-and-3mf.md](references/assembly-and-3mf.md) — Assembly joints, reference format, 3MF export for printing
10. [curves-and-curved-shapes.md](references/curves-and-curved-shapes.md) — Installed Curves (0.6.71) and Curved Shapes (1.00.14) addons

### Bundled Script

`scripts/mesh_report.py` — mesh triage, safe repair, plane/cylinder fitting and deviation check. Run with
`freecadcmd ~/.claude/skills/freecad-scripts/scripts/mesh_report.py -- model.stl --repair`, or import it (see the mesh reference).
