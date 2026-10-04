# Images to CAD

Build a parametric FreeCAD model that matches a photo, drawing or screenshot. An image has no
scale and (for photos) perspective distortion, so the job is: establish scale, measure,
build with named parameters, then compare and correct.

## Workflow

1. **Establish scale first.** Find a known length in the image: a ruler or caliper, a standard
   part (M3 screw head, coin, credit card 85.60 x 53.98 mm), a dimension printed on a drawing,
   or a measurement the user gives. If nothing is available, ask for one real dimension. Never
   invent a scale silently.
2. **Judge the image type.** An orthographic drawing or a straight-on photo of a flat part can
   be measured directly. An angled photo cannot: state that the dimensions carry perspective
   error and ask for a straight-on view or extra known dimensions.
3. **Write a feature list before any code**: base profile, then each additive/subtractive
   feature, then patterns, in the order a machinist would make it. Note which dimensions are
   measured, which are standard values (M3 clearance 3.4 mm, 3 mm wall) and which are guesses.
4. **Put every dimension in a Spreadsheet alias** (see `partdesign-and-parameters.md`). No
   magic numbers buried in code, so the user can correct one value and the model follows.
5. **Build, screenshot, compare, correct.** After each feature, render a view
   (below) and compare it against the reference image; fix proportions before adding detail.
6. **Report uncertainty**: list every dimension as measured / standard / assumed, with the
   estimated error from the pixel-per-mm scale.

## Measuring from pixels (PIL + numpy + scipy are bundled; OpenCV is NOT)

Claude can look at an image directly for orientation and feature identification, but numbers
should come from pixels. This example finds a dark part on a light background and a reference
bar of known length, then reports sizes in mm. Verified on a synthetic image: 63.94 x 48.01 mm
and a 16.12 mm hole against true values of 64 x 48 x 16.

```python
from PIL import Image
import numpy as np
from scipy import ndimage

im = np.asarray(Image.open("photo.png").convert("L"), dtype=float)
mask = im < 128                        # tune the threshold per image; check it visually

def bbox(m):
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1

REF_MM = 50.0                          # real length of the reference object
ref = mask.copy(); ref[:450] = False   # here: reference bar sits below row 450
part = mask.copy(); part[450:] = False
rx0, _, rx1, _ = bbox(ref)
px_per_mm = (rx1 - rx0) / REF_MM

x0, y0, x1, y1 = bbox(part)
width_mm, height_mm = (x1 - x0) / px_per_mm, (y1 - y0) / px_per_mm

holes = ndimage.binary_fill_holes(part) & ~part       # light pixels enclosed by the part
labels, n = ndimage.label(holes)
for i in range(1, n + 1):
    ys, xs = np.nonzero(labels == i)
    dia = 2 * np.sqrt(len(xs) / np.pi) / px_per_mm
    cx, cy = (xs.mean() - x0) / px_per_mm, (ys.mean() - y0) / px_per_mm
    print(f"hole {i}: dia {dia:.2f} mm at ({cx:.2f}, {cy:.2f}) from the part's top-left")
```

Limits: thresholding fails on low contrast, shadows and glare; edges are anti-aliased so
expect roughly +/-1 px error; image Y points down, FreeCAD Y points up (flip when
transferring coordinates). Say which of these applies to the image at hand.

## Comparing the model with the reference

The `execute_code` MCP tool returns a screenshot of the model by default and accepts
`view_name` (Isometric, Front, Top, Right, Back, Left, Bottom). Choose the view that matches
the reference image, and compare the two explicitly: proportions, hole positions, wall
thicknesses, feature count. `get_view` returns a view without running code.

In a GUI session you can also save a view yourself: `FreeCADGui.ActiveDocument.ActiveView.saveImage(
"/path/view.png", 1200, 800, "White")` after `viewFront()` / `viewTop()` and `fitAll()`.

To compare quantitatively, save a straight-on view of the model (white background), threshold
it like the reference, scale it with the same `px_per_mm`, and compute the overlap of the two
masks (intersection over union). This outline is untested; verify the view and scale match
before trusting the number.

## Matching a shape you can see but cannot measure

- Prefer standard sizes and round numbers once the measured value is within the error bar
  (a measured 5.9 mm hole with +/-0.3 mm error is an M6 clearance or 6 mm, not 5.9).
- Match symmetry and repetition exactly: if features look equally spaced, use a pattern with
  one spacing parameter rather than separate positions.
- Build the main volume first; add fillets and chamfers last (they are the first thing to
  break when a parameter changes).
- When two interpretations fit the image, say so and build the simpler one, then offer the
  alternative.

## Reporting to the user

Give the scale source and its error, a table of each dimension with its status
(measured / standard / assumed), what could not be determined from the image (hidden faces,
wall thickness, depth), and the comparison result. Ask for the one missing measurement that
would remove the most uncertainty.
