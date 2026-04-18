"""Feature builders (v1 flat `btType` format).

Adapted from hedless/onshape-mcp (MIT). Undocumented quirks baked in:
  - `filterInnerLoops: true` on the sketch-region query
  - `defaultScope: true` on the extrude so cuts apply to all existing bodies
"""
from dataclasses import dataclass, field
from enum import Enum


class ExtrudeType(str, Enum):
    NEW = "NEW"
    ADD = "ADD"
    REMOVE = "REMOVE"
    INTERSECT = "INTERSECT"


class EndBound(str, Enum):
    BLIND = "BLIND"
    THROUGH_ALL = "THROUGH_ALL"
    UP_TO_NEXT = "UP_TO_NEXT"


class ChamferType(str, Enum):
    EQUAL_OFFSETS = "EQUAL_OFFSETS"
    TWO_OFFSETS = "TWO_OFFSETS"
    OFFSET_ANGLE = "OFFSET_ANGLE"


def _qty(param_id: str, expression: str) -> dict:
    return {
        "btType": "BTMParameterQuantity-147",
        "parameterId": param_id,
        "expression": expression,
    }


def _enum(param_id: str, enum_name: str, value: str) -> dict:
    return {
        "btType": "BTMParameterEnum-145",
        "parameterId": param_id,
        "enumName": enum_name,
        "value": value,
    }


def _bool(param_id: str, value: bool) -> dict:
    return {
        "btType": "BTMParameterBoolean-144",
        "parameterId": param_id,
        "value": value,
    }


@dataclass
class ChamferBuilder:
    """Chamfer a list of edges identified by deterministic ID.

    Edge IDs come from find_edges. For equal-offset (the common case) only
    `width` matters. Tangent propagation extends the chamfer across tangent
    edges — leave off for hard "only these edges" behavior.
    """
    edge_ids: list
    name: str = "Chamfer"
    chamfer_type: ChamferType = ChamferType.EQUAL_OFFSETS
    width: str = "2 mm"
    # For TWO_OFFSETS / OFFSET_ANGLE; ignored for EQUAL_OFFSETS.
    width2: str = "2 mm"
    angle: str = "45 deg"
    tangent_propagation: bool = False

    def build(self) -> dict:
        queries = [{
            "btType": "BTMIndividualQuery-138",
            "deterministicIds": list(self.edge_ids),
        }]
        params = [
            {
                "btType": "BTMParameterQueryList-148",
                "parameterId": "entities",
                "queries": queries,
            },
            _enum("chamferType", "ChamferType", self.chamfer_type.value),
            _qty("width", self.width),
            _bool("tangentPropagation", self.tangent_propagation),
        ]
        if self.chamfer_type == ChamferType.TWO_OFFSETS:
            params.append(_qty("width2", self.width2))
        elif self.chamfer_type == ChamferType.OFFSET_ANGLE:
            params.append(_qty("angle", self.angle))
        return {
            "btType": "BTMFeature-134",
            "featureType": "chamfer",
            "name": self.name,
            "parameters": params,
        }


@dataclass
class ExtrudeBuilder:
    """Extrude a sketch region. `sketch_feature_id` is the id returned by add_feature."""
    sketch_feature_id: str
    name: str = "Extrude"
    operation: ExtrudeType = ExtrudeType.NEW
    end_bound: EndBound = EndBound.BLIND
    depth: str = "25 mm"
    # Flip the extrude along the face normal. When sketching on a body's top
    # face (normal pointing +Z), a REMOVE extrude with opposite_direction=False
    # cuts UPWARD out of the body (useless). Setting this True makes the cut
    # go down INTO the body — usually what the user wants for holes/recesses.
    # See tools/features.py `_create_extrude` for auto-resolution from a
    # target-direction vector + face normal.
    opposite_direction: bool = False
    second_direction: bool = False
    second_end_bound: EndBound = EndBound.BLIND
    second_depth: str = "25 mm"
    region_entity_ids: list = field(default_factory=list)

    def _region_query(self) -> dict:
        if self.region_entity_ids:
            queries = [{
                "btType": "BTMIndividualSketchRegionQuery-140",
                "featureId": self.sketch_feature_id,
                "queryStatement": None,
                "queryString": "",
                "entityId": eid,
                "filterInnerLoops": True,
            } for eid in self.region_entity_ids]
        else:
            queries = [{
                "btType": "BTMIndividualSketchRegionQuery-140",
                "featureId": self.sketch_feature_id,
                "filterInnerLoops": True,
            }]
        return {
            "btType": "BTMParameterQueryList-148",
            "parameterId": "entities",
            "queries": queries,
        }

    def build(self) -> dict:
        params = [
            self._region_query(),
            _enum("bodyType", "ExtendedToolBodyType", "SOLID"),
            _enum("operationType", "NewBodyOperationType", self.operation.value),
            _bool("defaultScope", True),
            _bool("oppositeDirection", self.opposite_direction),
            _enum("endBound", "BoundingType", self.end_bound.value),
        ]
        if self.end_bound == EndBound.BLIND:
            params.append(_qty("depth", self.depth))
        params.append(_bool("hasSecondDirection", self.second_direction))
        if self.second_direction:
            params.append(_enum("secondDirectionBound", "BoundingType",
                                self.second_end_bound.value))
            if self.second_end_bound == EndBound.BLIND:
                params.append(_qty("secondDirectionDepth", self.second_depth))
        return {
            "btType": "BTMFeature-134",
            "featureType": "extrude",
            "name": self.name,
            "parameters": params,
        }
