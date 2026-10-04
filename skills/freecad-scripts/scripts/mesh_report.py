# -*- coding: utf-8 -*-
"""Mesh triage, safe repair, primitive fitting and deviation check for FreeCAD 1.1.

Run headless:
    freecadcmd scripts/mesh_report.py -- model.stl [--repair] [--min-component 20] [--json out.json]

Or import from a script / execute_code:
    sys.path.insert(0, "<skill>/scripts"); import mesh_report as mr

Needs only FreeCAD's bundled Python (numpy included). Not valid for GUI-only calls.
"""
import json
import math
import sys

import FreeCAD
import Mesh
import numpy as np
import Part

# Planes: Mesh.getSegmentsOfType works well (deviation 0.05). Mesh's own cylinder segmentation
# shatters even a perfect cylinder into fragments, so cylinders use the RANSAC fit below.
PLANE_DEV = 0.05
NO_NEIGHBOUR = 4294967295


def load(path):
    """Load a mesh file (STL/OBJ/PLY/3MF...) as a Mesh.Mesh."""
    return Mesh.Mesh(path)


def triage(mesh):
    """Return a dict describing mesh health. Never modifies the mesh."""
    bb = mesh.BoundBox
    comps = sorted((c.CountFacets for c in mesh.getSeparateComponents()), reverse=True)
    dims = (bb.XLength, bb.YLength, bb.ZLength)
    report = {
        "facets": mesh.CountFacets,
        "points": mesh.CountPoints,
        "bbox_mm": [round(d, 4) for d in dims],
        "volume": mesh.Volume,
        "area": mesh.Area,
        "is_solid": mesh.isSolid(),
        "non_manifold": mesh.hasNonManifolds(),
        "self_intersections": mesh.hasSelfIntersections(),
        "non_uniform_normals": mesh.countNonUniformOrientedFacets(),
        "components": len(comps),
        "component_sizes_top": comps[:8],
        "tiny_components": sum(1 for c in comps if c <= 20),
        "corrupted_facets": mesh.hasCorruptedFacets(),
    }
    notes = []
    if max(dims) < 1.0:
        notes.append("largest dimension < 1 mm: file may be in metres; check units")
    if max(dims) > 2000.0:
        notes.append("largest dimension > 2 m: file may be in micrometres; check units")
    if report["tiny_components"]:
        notes.append("debris components present; repair with --repair or removeComponents(n)")
    if report["non_manifold"]:
        notes.append("non-manifold edges: removeNonManifolds()")
    if report["non_uniform_normals"]:
        notes.append("inconsistent normals: harmonizeNormals()")
    if not report["is_solid"]:
        notes.append("mesh is not a closed solid: volume figures are unreliable")
    if report["self_intersections"]:
        notes.append("self-intersections: fixSelfIntersections() may help but can remove facets")
    report["notes"] = notes
    return report


def repair(mesh, min_component_facets=20):
    """Apply only non-destructive repairs to a COPY. Returns (mesh, step_log).

    Deliberately excludes removeNeedles/optimizeTopology/removeFoldsOnSurface: on a
    real scan removeNeedles deleted ~25% of facets and optimizeTopology re-introduced
    self-intersections. Call those yourself and compare the logged facet/volume change.
    """
    m = mesh.copy()
    log = []

    def step(name, fn):
        before = (m.CountFacets, m.Volume)
        fn()
        log.append({"step": name, "facets": [before[0], m.CountFacets],
                    "volume": [round(before[1], 3), round(m.Volume, 3)]})

    step("removeDuplicatedPoints", m.removeDuplicatedPoints)
    step("removeDuplicatedFacets", m.removeDuplicatedFacets)
    step("removeComponents", lambda: m.removeComponents(min_component_facets))
    step("harmonizeNormals", m.harmonizeNormals)
    step("fixDegenerations", m.fixDegenerations)
    step("removeNonManifolds", m.removeNonManifolds)
    step("fixIndices", m.fixIndices)
    return m, log


# ---------------------------------------------------------------- fitting
def _segment_points(mesh, facet_indices):
    facets = mesh.Facets
    pts = np.array([tuple(p) for i in facet_indices for p in facets[i].Points])
    return np.unique(np.round(pts, 6), axis=0)


def fit_plane(pts):
    c = pts.mean(0)
    n = np.linalg.svd(pts - c)[2][2]
    d = (pts - c) @ n
    return {"type": "Plane", "point": c.tolist(), "normal": n.tolist(),
            "rms": float(np.sqrt((d ** 2).mean())), "max": float(np.abs(d).max())}


def fit_sphere(pts):
    A = np.c_[2 * pts, np.ones(len(pts))]
    b = (pts ** 2).sum(1)
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    center = sol[:3]
    r = math.sqrt(max(sol[3] + center @ center, 0.0))
    d = np.linalg.norm(pts - center, axis=1) - r
    return {"type": "Sphere", "center": center.tolist(), "radius": r,
            "rms": float(np.sqrt((d ** 2).mean())), "max": float(np.abs(d).max())}


def fit_cylinder(pts, normals):
    """Axis = direction least explained by the facet normals; then a circle fit."""
    axis = np.linalg.eigh(normals.T @ normals)[1][:, 0]
    c0 = pts.mean(0)
    u = np.cross(axis, [1.0, 0.0, 0.0])
    if np.linalg.norm(u) < 1e-6:
        u = np.cross(axis, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    w = np.cross(axis, u)
    xy = np.c_[(pts - c0) @ u, (pts - c0) @ w]
    sol = np.linalg.lstsq(np.c_[2 * xy, np.ones(len(xy))], (xy ** 2).sum(1), rcond=None)[0]
    cx, cy = sol[:2]
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
    center = c0 + cx * u + cy * w
    d = np.linalg.norm(np.cross(pts - center, axis), axis=1) - r
    return {"type": "Cylinder", "axis": axis.tolist(), "point": center.tolist(), "radius": r,
            "rms": float(np.sqrt((d ** 2).mean())), "max": float(np.abs(d).max())}


def _grade(fit, diagonal):
    """good / marginal / poor. Curved fits are judged against their radius, planes
    against the mesh diagonal. A 'poor' cylinder is usually freeform, not a cylinder."""
    scale = fit["radius"] if "radius" in fit else diagonal
    ratio = fit["rms"] / max(scale, 1e-9)
    limits = (0.005, 0.03) if "radius" in fit else (0.0005, 0.003)
    return "good" if ratio < limits[0] else "marginal" if ratio < limits[1] else "poor"


def _facet_arrays(mesh):
    facets = mesh.Facets
    n = len(facets)
    cent = np.empty((n, 3)); norm = np.empty((n, 3)); nbrs = []
    for i in range(n):
        f = facets[i]
        p = f.Points
        cent[i] = ((p[0][0] + p[1][0] + p[2][0]) / 3, (p[0][1] + p[1][1] + p[2][1]) / 3,
                   (p[0][2] + p[1][2] + p[2][2]) / 3)
        norm[i] = tuple(f.Normal)
        nbrs.append([k for k in f.NeighbourIndices if k != NO_NEIGHBOUR])
    return cent, norm, nbrs


def _largest_connected(members, nbrs):
    """Largest group of `members` (set of facet ids) connected through shared edges."""
    seen, best = set(), []
    for start in members:
        if start in seen:
            continue
        comp, stack = [], [start]
        seen.add(start)
        while stack:
            k = stack.pop()
            comp.append(k)
            for q in nbrs[k]:
                if q in members and q not in seen:
                    seen.add(q)
                    stack.append(q)
        if len(comp) > len(best):
            best = comp
    return best


def _local_facets(start, nbrs, free_set, depth):
    """Unclaimed facets within `depth` edge-hops of `start` (likely the same surface)."""
    seen, frontier = {start}, [start]
    for _ in range(depth):
        nxt = []
        for k in frontier:
            for q in nbrs[k]:
                if q in free_set and q not in seen:
                    seen.add(q)
                    nxt.append(q)
        frontier = nxt
    return list(seen)


def _circle_through(p1, p2, p3):
    """Circumcentre and radius of three 2D points, or None if collinear."""
    ax, ay = p1; bx, by = p2; cx, cy = p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def _ransac_cylinder(cent, norm, nbrs, free, diag, min_facets, tol_abs, iters, rng):
    """One RANSAC pass over the unclaimed facet ids `free` (np.array). Returns facet ids or [].

    Minimal sample = three facets from one local neighbourhood: two normals give the axis
    (their cross product), three centroids projected along it give a circle.
    """
    free_set = set(free.tolist())
    best = []
    for _ in range(iters):
        local = _local_facets(int(rng.choice(free)), nbrs, free_set, 5)
        if len(local) < 3:
            continue
        i, j, k = rng.choice(local, 3, replace=False)
        axis = np.cross(norm[i], norm[j])
        length = np.linalg.norm(axis)
        if length < 0.1:                       # normals nearly parallel: axis undefined
            continue
        axis /= length
        if abs(norm[k] @ axis) > 0.05:         # third facet must also be parallel to the axis
            continue
        u = np.cross(axis, [1.0, 0.0, 0.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(axis, [0.0, 1.0, 0.0])
        u /= np.linalg.norm(u)
        w = np.cross(axis, u)
        proj = [(cent[q] @ u, cent[q] @ w) for q in (i, j, k)]
        circ = _circle_through(*proj)
        if circ is None:
            continue
        (cu, cv), r = circ
        if r > diag or r < 1e-6:
            continue
        center = cu * u + cv * w                # on the axis line (offset along axis irrelevant)
        rel = cent[free] - center
        rel -= np.outer(rel @ axis, axis)
        dist = np.linalg.norm(rel, axis=1)
        radial = rel / np.maximum(dist[:, None], 1e-12)
        ok = ((np.abs(norm[free] @ axis) < 0.05)
              & (np.abs(dist - r) < max(tol_abs, 0.03 * r))
              & (np.abs(np.einsum("ij,ij->i", radial, norm[free])) > 0.9))
        members = set(free[ok].tolist())
        if len(members) <= len(best):
            continue
        comp = _largest_connected(members, nbrs)
        if len(comp) > len(best):
            best = comp
    return best if len(best) >= min_facets else []


def fit_primitives(mesh, min_facets=30, tol=None, iterations=600, max_cylinders=30, seed=0):
    """Fit planes (Mesh segmentation) and cylinders (RANSAC) to a mesh.

    Planes are claimed first, then cylinders from the remaining facets. Returns
    (fits, coverage); coverage is the fraction of facets explained by a primitive. The
    remainder is freeform: use ReverseEngineering.approxSurface or model it by hand.
    `tol` is the absolute cylinder inlier tolerance in mm (default 0.2% of the bbox diagonal,
    but never tighter than 3% of the fitted radius).
    Spheres are not fitted here; use fit_sphere on points you have already isolated.
    """
    diag = mesh.BoundBox.DiagonalLength
    tol = 0.002 * diag if tol is None else tol
    rng = np.random.default_rng(seed)
    cent, norm, nbrs = _facet_arrays(mesh)
    claimed = set()
    fits = []
    for seg in mesh.getSegmentsOfType("Plane", PLANE_DEV, min_facets):
        fresh = [i for i in seg if i not in claimed]
        if len(fresh) < min_facets or len(fresh) < 0.5 * len(seg):
            continue
        fit = fit_plane(_segment_points(mesh, fresh))
        fit["facets"] = len(fresh)
        fit["quality"] = _grade(fit, diag)
        fits.append(fit)
        claimed.update(fresh)
    for _ in range(max_cylinders):
        free = np.array([i for i in range(mesh.CountFacets) if i not in claimed])
        if len(free) < min_facets:
            break
        ids = _ransac_cylinder(cent, norm, nbrs, free, diag, min_facets, tol, iterations, rng)
        if not ids:
            break
        fit = fit_cylinder(_segment_points(mesh, ids), norm[ids])
        fit["facets"] = len(ids)
        fit["quality"] = _grade(fit, diag)
        fits.append(fit)
        claimed.update(ids)
    return fits, len(claimed) / max(mesh.CountFacets, 1)


# -------------------------------------------------------------- deviation
def deviation(mesh, shape, samples=1500, tol=0.1, seed=0):
    """Distance from sampled mesh vertices to the SURFACE of a rebuilt shape.

    Uses the faces (not the solid) so interior points do not read as zero.
    """
    rng = np.random.default_rng(seed)
    pts = mesh.Points
    idx = rng.choice(len(pts), size=min(samples, len(pts)), replace=False)
    surface = Part.Compound(shape.Faces)
    d = np.array([surface.distToShape(Part.Vertex(pts[i].Vector))[0] for i in idx])
    return {"samples": len(d), "mean": float(d.mean()), "rms": float(np.sqrt((d ** 2).mean())),
            "p95": float(np.percentile(d, 95)), "max": float(d.max()),
            "within_tol": float((d <= tol).mean()), "tol": tol}


def main(argv):
    args = [a for a in argv if a != "--"]
    if not args:
        print("usage: freecadcmd mesh_report.py -- file [--repair] [--min-component N] [--json out]")
        return 2
    path = args[0]
    do_repair = "--repair" in args
    min_comp = int(args[args.index("--min-component") + 1]) if "--min-component" in args else 20
    out = {"file": path, "triage": triage(load(path))}
    mesh = load(path)
    if do_repair:
        mesh, out["repair_log"] = repair(mesh, min_comp)
        out["triage_after_repair"] = triage(mesh)
    fits, coverage = fit_primitives(mesh)
    out["coverage"] = round(coverage, 3)
    out["fits"] = fits
    text = json.dumps(out, indent=2)
    if "--json" in args:
        with open(args[args.index("--json") + 1], "w") as fh:
            fh.write(text)
    print(text)
    return 0


if any(a.endswith("mesh_report.py") for a in sys.argv):   # launched via freecadcmd, not imported
    import os
    rc = main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    sys.stdout.flush()
    os._exit(rc)
