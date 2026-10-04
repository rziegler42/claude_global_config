# FreeCAD Workbenches and Advanced Topics

Reference guide for workbench creation, macros, FEM scripting, Path/CAM scripting, and advanced recipes.

## Official Wiki References

- [Workbench creation](https://wiki.freecad.org/Workbench_creation)
- [Script tutorial](https://wiki.freecad.org/Scripts)
- [Macros recipes](https://wiki.freecad.org/Macros_recipes)
- [FEM scripting](https://wiki.freecad.org/FEM_Tutorial_Python)
- [Path scripting](https://wiki.freecad.org/Path_scripting)
- [Svg namespace](https://wiki.freecad.org/Svg_Namespace)
- [Python](https://wiki.freecad.org/Python)
- [PythonOCC](https://wiki.freecad.org/PythonOCC)

## Custom Workbench — Full Template

### Directory Structure

```
MyWorkbench/
├── __init__.py          # Empty or minimal
├── Init.py              # Runs at FreeCAD startup (no GUI)
├── InitGui.py           # Runs at GUI startup (defines workbench)
├── MyCommands.py        # Command implementations
├── Resources/
│   ├── icons/
│   │   ├── MyWorkbench.svg
│   │   └── MyCommand.svg
│   └── translations/    # Optional i18n
└── README.md
```

### Init.py

```python
# Runs at FreeCAD startup (before GUI)
# Register importers/exporters, add module paths, etc.
import FreeCAD
FreeCAD.addImportType("My Format (*.myf)", "MyImporter")
FreeCAD.addExportType("My Format (*.myf)", "MyExporter")
```

### InitGui.py

```python
import FreeCADGui

class MyWorkbench(FreeCADGui.Workbench):
    """Custom FreeCAD workbench."""

    MenuText = "My Workbench"
    ToolTip = "A custom workbench for specialized tasks"

    def __init__(self):
        import os
        self.__class__.Icon = os.path.join(
            os.path.dirname(__file__), "Resources", "icons", "MyWorkbench.svg"
        )

    def Initialize(self):
        """Called when workbench is first activated."""
        import MyCommands  # deferred import

        # Define toolbars
        self.appendToolbar("My Tools", [
            "My_CreateBox",
            "Separator",    # toolbar separator
            "My_EditObject"
        ])

        # Define menus
        self.appendMenu("My Workbench", [
            "My_CreateBox",
            "My_EditObject"
        ])

        # Submenus
        self.appendMenu(["My Workbench", "Advanced"], [
            "My_AdvancedCommand"
        ])

        import FreeCAD
        FreeCAD.Console.PrintMessage("My Workbench initialized\n")

    def Activated(self):
        """Called when workbench is switched to."""
        pass

    def Deactivated(self):
        """Called when leaving the workbench."""
        pass

    def ContextMenu(self, recipient):
        """Called for right-click context menus."""
        self.appendContextMenu("My Tools", ["My_CreateBox"])

    def GetClassName(self):
        return "Gui::PythonWorkbench"

FreeCADGui.addWorkbench(MyWorkbench)
```

### MyCommands.py

```python
import FreeCAD
import FreeCADGui
import os

ICON_PATH = os.path.join(os.path.dirname(__file__), "Resources", "icons")

class CmdCreateBox:
    def GetResources(self):
        return {
            "Pixmap": os.path.join(ICON_PATH, "MyCommand.svg"),
            "MenuText": "Create Box",
            "ToolTip": "Create a parametric box"
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        import Part
        doc = FreeCAD.ActiveDocument
        box = Part.makeBox(10, 10, 10)
        Part.show(box, "MyBox")
        doc.recompute()

class CmdEditObject:
    def GetResources(self):
        return {
            "Pixmap": ":/icons/edit-undo.svg",
            "MenuText": "Edit Object",
            "ToolTip": "Edit selected object"
        }

    def IsActive(self):
        return len(FreeCADGui.Selection.getSelection()) > 0

    def Activated(self):
        sel = FreeCADGui.Selection.getSelection()[0]
        FreeCAD.Console.PrintMessage(f"Editing {sel.Name}\n")

# Register commands
FreeCADGui.addCommand("My_CreateBox", CmdCreateBox())
FreeCADGui.addCommand("My_EditObject", CmdEditObject())
```

### Installing a Workbench

Place the workbench folder in one of:

```python
# User macro folder
FreeCAD.getUserMacroDir(True)

# User mod folder (preferred)
os.path.join(FreeCAD.getUserAppDataDir(), "Mod")

# System mod folder
os.path.join(FreeCAD.getResourceDir(), "Mod")
```

## FEM Scripting

Verified end to end in FreeCAD 1.1.4 (CalculiX static analysis, returns one result object).
The mesh must be generated explicitly before solving.

```python
import FreeCAD, Part, ObjectsFem, Fem

doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("FEM")

# Solid to analyse (replace with an existing document object)
obj = doc.addObject("Part::Feature", "Beam")
obj.Shape = Part.makeBox(100, 10, 10)
doc.recompute()

analysis = ObjectsFem.makeAnalysis(doc, "Analysis")

# Solver (ccxtools workflow; ObjectsFem.makeSolverCalculiX is the newer framework solver)
solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "Solver")
solver.AnalysisType = "static"
solver.GeometricalNonlinearity = "linear"
solver.ThermoMechSteadyState = False
solver.MatrixSolverType = "default"
analysis.addObject(solver)

# Material
material = ObjectsFem.makeMaterialSolid(doc, "Steel")
mat = material.Material
mat["Name"] = "Steel"
mat["YoungsModulus"] = "210000 MPa"
mat["PoissonRatio"] = "0.3"
mat["Density"] = "7900 kg/m^3"
material.Material = mat
analysis.addObject(material)

# Fixed constraint
fixed = ObjectsFem.makeConstraintFixed(doc, "Fixed")
fixed.References = [(obj, "Face1")]
analysis.addObject(fixed)

# Force constraint (direction is an edge or face of the solid)
force = ObjectsFem.makeConstraintForce(doc, "Force")
force.References = [(obj, "Face2")]
force.Force = 1000.0  # Newtons
force.Direction = (obj, ["Edge2"])
force.Reversed = False
analysis.addObject(force)

# Mesh: the property is Shape (not Part)
mesh = ObjectsFem.makeMeshGmsh(doc, "FEMMesh")
mesh.Shape = obj
mesh.CharacteristicLengthMax = 5.0
analysis.addObject(mesh)
doc.recompute()

# Generate the mesh (without this the solver fails: node set FIXED does not exist)
from femmesh.gmshtools import GmshTools
err = GmshTools(mesh).create_mesh()   # None on success
doc.recompute()

# Run the solver
from femtools import ccxtools
fea = ccxtools.FemToolsCcx(analysis, solver)
fea.update_objects()
fea.setup_working_dir()
fea.setup_ccx()
msg = fea.check_prerequisites()       # "" when ready
if not msg:
    fea.purge_results()
    fea.write_inp_file()
    fea.ccx_run()                     # returns 0 on success
    fea.load_results()
    results = [o for o in doc.Objects if o.TypeId.startswith("Fem::FemResultObject")]
    print(max(results[0].DisplacementLengths))
```

## CAM Scripting (Python module is still `Path`)

```python
import Path
import FreeCAD

# Create a path
commands = []
commands.append(Path.Command("G0", {"X": 0, "Y": 0, "Z": 5}))   # Rapid move
commands.append(Path.Command("G1", {"X": 10, "Y": 0, "Z": 0, "F": 100}))  # Feed
commands.append(Path.Command("G1", {"X": 10, "Y": 10, "Z": 0}))
commands.append(Path.Command("G1", {"X": 0, "Y": 10, "Z": 0}))
commands.append(Path.Command("G1", {"X": 0, "Y": 0, "Z": 0}))
commands.append(Path.Command("G0", {"Z": 5}))   # Retract

path = Path.Path(commands)

# Add to document
doc = FreeCAD.ActiveDocument
path_obj = doc.addObject("Path::Feature", "MyPath")
path_obj.Path = path

# G-code output
gcode = path.toGCode()
print(gcode)
```

## Common Recipes

### Mirror a Shape

```python
import Part
import FreeCAD
shape = obj.Shape
mirrored = shape.mirror(FreeCAD.Vector(0,0,0), FreeCAD.Vector(1,0,0))  # mirror about YZ
Part.show(mirrored, "Mirrored")
```

### Array of Shapes

```python
import Part
import FreeCAD

def linear_array(shape, direction, count, spacing):
    """Create a linear array compound."""
    shapes = []
    for i in range(count):
        offset = FreeCAD.Vector(direction)
        offset.multiply(i * spacing)
        moved = shape.copy()
        moved.translate(offset)
        shapes.append(moved)
    return Part.Compound(shapes)

result = linear_array(obj.Shape, FreeCAD.Vector(1,0,0), 5, 15.0)
Part.show(result, "Array")
```

### Circular/Polar Array

```python
import Part
import FreeCAD
import math

def polar_array(shape, axis, center, count):
    """Create a polar array compound."""
    shapes = []
    angle = 360.0 / count
    for i in range(count):
        rot = FreeCAD.Rotation(axis, angle * i)
        placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), rot, center)
        moved = shape.copy()
        moved.Placement = placement
        shapes.append(moved)
    return Part.Compound(shapes)

result = polar_array(obj.Shape, FreeCAD.Vector(0,0,1), FreeCAD.Vector(0,0,0), 8)
Part.show(result, "PolarArray")
```

### Measure Distance Between Shapes

```python
dist = shape1.distToShape(shape2)
# Returns: (min_distance, [(point_on_shape1, point_on_shape2), ...], ...)
min_dist = dist[0]
closest_points = dist[1]  # List of (Vector, Vector) pairs
```

### Create a Tube/Pipe

```python
import Part

outer_cyl = Part.makeCylinder(outer_radius, height)
inner_cyl = Part.makeCylinder(inner_radius, height)
tube = outer_cyl.cut(inner_cyl)
Part.show(tube, "Tube")
```

### Assign Color to Faces

```python
# Per-face colors: one FreeCAD.Material per face (1.x API; DiffuseColor is legacy)
def face_material(rgb):
    m = FreeCAD.Material()
    m.DiffuseColor = (*rgb, 1.0)
    return m

obj.ViewObject.ShapeAppearance = [
    face_material((1.0, 0.0, 0.0)),   # Face1 = red
    face_material((0.0, 1.0, 0.0)),   # Face2 = green
    face_material((0.0, 0.0, 1.0)),   # Face3 = blue
    # ... one Material per face
]

# Or set a single color / transparency (0-100) for the whole object
obj.ViewObject.ShapeColor = (0.8, 0.2, 0.2)
obj.ViewObject.Transparency = 40
```

### Batch Export All Objects

```python
import FreeCAD
import Part
import os

doc = FreeCAD.ActiveDocument
export_dir = "/path/to/export"

if doc is None:
    FreeCAD.Console.PrintMessage("No active document to export.\n")
else:
    os.makedirs(export_dir, exist_ok=True)

    for obj in doc.Objects:
        if hasattr(obj, "Shape") and obj.Shape.Solids:
            filepath = os.path.join(export_dir, f"{obj.Name}.step")
            Part.export([obj], filepath)
            FreeCAD.Console.PrintMessage(f"Exported {filepath}\n")
```

### Timer / Progress Bar

```python
from PySide import QtWidgets, QtCore

# Simple progress dialog
progress = QtWidgets.QProgressDialog("Processing...", "Cancel", 0, total_steps)
progress.setWindowModality(QtCore.Qt.WindowModal)

for i in range(total_steps):
    if progress.wasCanceled():
        break
    # ... do work ...
    progress.setValue(i)

progress.setValue(total_steps)
```

### Run a Macro Programmatically

```python
import FreeCADGui
import runpy

# Execute a macro file
FreeCADGui.runCommand("Std_DlgMacroExecute")  # Opens macro dialog

# Only execute trusted macros. Prefer an explicit path and a clearer runner.
runpy.run_path("/path/to/macro.py", run_name="__main__")

# Or use the FreeCAD macro runner with the same trusted, explicit path
FreeCADGui.doCommand('import runpy; runpy.run_path("/path/to/macro.py", run_name="__main__")')
```
