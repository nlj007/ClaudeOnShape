"""Sketch feature builders (v1 flat `btType` format).

A Sketch is itself a feature (`BTMSketch-151`) whose `geometry` holds curve
entities. Circles are encoded as TWO semicircular arc segments (startParam
0→π and π→2π) — that's what the Onshape UI emits and what downstream sketch
region queries expect.

Adapted from hedless/onshape-mcp (MIT).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math
import uuid


class SketchPlane(str, Enum):
    # Deterministic IDs of the default construction planes. These are identical
    # in EVERY Part Studio (verified by FS probe against a fresh studio). They
    # refer to the origin/construction planes, NOT faces of created bodies.
    #
    # WARNING: earlier code used JHD/JFD/JGD — those turned out to be
    # deterministic IDs of faces on the FIRST extruded body (happened to align
    # with the top/front/right faces of a cube centered on origin). That
    # silently worked until a later feature modified the face, producing a
    # "Missing Part of Extrude 1" error. If you ever need to sketch on a
    # body face, DO NOT hardcode an ID — use find_faces() to resolve one.
    TOP = "JDC"
    FRONT = "JCC"
    RIGHT = "JEC"


def _uid(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


@dataclass
class SketchBuilder:
    """Build a Sketch feature. Add geometry, then call `build()`."""
    name: str = "Sketch"
    plane: SketchPlane = SketchPlane.TOP
    # Override plane with an arbitrary deterministic ID (e.g. a body face
    # returned by find_faces). When set, takes precedence over `plane`.
    plane_id: str | None = None
    entities: list = field(default_factory=list)

    def add_circle(self, cx: float, cy: float, radius: float,
                   entity_id: str | None = None) -> str:
        """Add a circle centered at (cx, cy) in meters. Returns entity id."""
        eid = entity_id or _uid("circle_")
        geometry = {
            "btType": "BTCurveGeometryCircle-115",
            "radius": radius,
            "xCenter": cx,
            "yCenter": cy,
            "xDir": 1.0,
            "yDir": 0.0,
            "clockwise": False,
        }
        for idx, (start, end) in enumerate(((0.0, math.pi), (math.pi, 2 * math.pi))):
            self.entities.append({
                "btType": "BTMSketchCurveSegment-155",
                "entityId": f"{eid}.{idx}",
                "startParam": start,
                "endParam": end,
                "startPointId": f"{eid}.start{idx}",
                "endPointId": f"{eid}.end{idx}",
                "centerId": f"{eid}.center",
                "geometry": geometry,
            })
        return eid

    def add_rectangle(self, cx: float, cy: float, width: float, height: float,
                      entity_id: str | None = None) -> str:
        """Add a centered rectangle (width along U, height along V) in METERS.

        Four line segments in CCW order: bottom, right, top, left. Shared
        endpoint IDs at each corner so the sketch closes into a single
        region — required for extrude region-query resolution.
        """
        eid = entity_id or _uid("rect_")
        hw, hh = width / 2.0, height / 2.0
        # Corner points in UV (local sketch) coords, CCW from bottom-left.
        corners = [
            (cx - hw, cy - hh),  # 0 BL
            (cx + hw, cy - hh),  # 1 BR
            (cx + hw, cy + hh),  # 2 TR
            (cx - hw, cy + hh),  # 3 TL
        ]
        pt_ids = [f"{eid}.p{i}" for i in range(4)]
        for i in range(4):
            a, b = corners[i], corners[(i + 1) % 4]
            # Unit direction + length. Endpoints are parameterized by arc
            # length along the line (startParam=0, endParam=length).
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = (dx * dx + dy * dy) ** 0.5
            udx, udy = dx / length, dy / length
            self.entities.append({
                "btType": "BTMSketchCurveSegment-155",
                "entityId": f"{eid}.l{i}",
                "startParam": 0.0,
                "endParam": length,
                "startPointId": pt_ids[i],
                "endPointId": pt_ids[(i + 1) % 4],
                "geometry": {
                    "btType": "BTCurveGeometryLine-117",
                    "pntX": a[0],
                    "pntY": a[1],
                    "dirX": udx,
                    "dirY": udy,
                },
            })
        return eid

    def build(self) -> dict:
        plane_det_id = self.plane_id or self.plane.value
        return {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": self.name,
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "parameterId": "sketchPlane",
                    "queries": [{
                        "btType": "BTMIndividualQuery-138",
                        "deterministicIds": [plane_det_id],
                    }],
                },
                {
                    "btType": "BTMParameterBoolean-144",
                    "parameterId": "disableImprinting",
                    "value": False,
                },
            ],
            "entities": self.entities,
        }
