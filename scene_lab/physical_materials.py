"""DexJoCo-style physical material inference for imported Scene Lab assets."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEXJOCO_MATERIALS: dict[str, dict[str, Any]] = {
    "default_rigid": {
        "surface_type": "default_rigid",
        "source": "dexjoco_move_book_style",
        "contact": {
            "condim": 3,
            "friction": [1.0, 0.03, 0.0005],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "table": {
        "surface_type": "table",
        "source": "dexjoco_move_book_table",
        "contact": {
            "condim": 3,
            "friction": [1.2, 0.01, 0.0001],
            "group": 3,
        },
    },
    "plastic_graspable": {
        "surface_type": "plastic",
        "source": "dexjoco_move_book_style",
        "contact": {
            "condim": 4,
            "contype": 1,
            "conaffinity": 14,
            "friction": [1.0, 0.03, 0.0005],
            "solref": [0.002, 1.0],
            "solimp": [0.9, 0.95, 0.001],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "tool_rubber_metal": {
        "surface_type": "rubber_metal",
        "source": "dexjoco_camera_style",
        "contact": {
            "condim": 4,
            "contype": 1,
            "conaffinity": 14,
            "friction": [0.8, 0.02, 0.002],
            "solref": [0.002, 1.0],
            "solimp": [0.9, 0.95, 0.001],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "glass_ceramic": {
        "surface_type": "glass_ceramic",
        "source": "dexjoco_glass_style",
        "contact": {
            "condim": 4,
            "contype": 1,
            "conaffinity": 14,
            "friction": [0.9, 0.2, 0.2],
            "solref": [0.001, 2.0],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "paper_cardboard": {
        "surface_type": "paper_cardboard",
        "source": "dexjoco_move_book_style",
        "contact": {
            "condim": 4,
            "contype": 1,
            "conaffinity": 14,
            "friction": [1.0, 0.03, 0.0005],
            "solref": [0.002, 1.0],
            "solimp": [0.9, 0.95, 0.001],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
    "soft_visual_rigid_collision": {
        "surface_type": "soft_visual_rigid_collision",
        "source": "dexjoco_plant_style",
        "contact": {
            "condim": 4,
            "contype": 1,
            "conaffinity": 14,
            "friction": [0.95, 0.3, 0.1],
            "solref": [0.001, 1.0],
            "solimp": [0.998, 0.998, 0.001],
            "group": 3,
            "rgba": [0.0, 0.0, 0.0, 0.0],
        },
    },
}


TOKEN_TO_MATERIAL = (
    (("plant", "flower"), "soft_visual_rigid_collision"),
    (("glass", "bowl", "plate", "cup", "mug"), "glass_ceramic"),
    (("box", "carton", "tissue", "book", "board", "paper"), "paper_cardboard"),
    (("hammer", "drill", "screwdriver", "fork", "knife", "scissor", "wrench"), "tool_rubber_metal"),
    (("camera", "scanner", "speaker", "mouse", "phone", "remote"), "tool_rubber_metal"),
    (("bottle", "can", "plastic", "shampoo", "tube", "bucket", "basket", "tray"), "plastic_graspable"),
)


def infer_material_key(category: str, asset_id: str = "") -> str:
    haystack = f"{category} {asset_id}".lower()
    for tokens, material_key in TOKEN_TO_MATERIAL:
        if any(token in haystack for token in tokens):
            return material_key
    return "default_rigid"


def infer_physical_material(asset_manifest: dict[str, Any]) -> dict[str, Any]:
    category = str(asset_manifest.get("category") or "")
    asset_id = str(asset_manifest.get("asset_id") or "")
    key = infer_material_key(category, asset_id)
    material = deepcopy(DEXJOCO_MATERIALS[key])
    material["material_key"] = key
    material["asset_id"] = asset_id
    material["category"] = category
    material["engine"] = "mujoco"
    material["model"] = "dexjoco_geom_contact"
    return material


def contact_attrs(material: dict[str, Any]) -> dict[str, Any]:
    return dict(material.get("contact") or {})
