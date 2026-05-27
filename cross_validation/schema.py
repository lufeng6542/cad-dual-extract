# -*- coding: utf-8 -*-
"""统一数据模型 - 方案A和方案B的共同输出格式"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum


class ItemType(str, Enum):
    TEXT = "text"
    PIPE = "pipe"
    EQUIPMENT = "equipment"
    DIMENSION = "dimension"
    ROOM_LABEL = "room_label"


@dataclass
class TextItem:
    content: str
    position: Optional[Tuple[float, float, float]] = None
    layer: Optional[str] = None
    height: Optional[float] = None
    text_type: Optional[str] = None  # room_name, pipe_label, dimension_value, etc.
    confidence: float = 1.0
    source: str = ""


@dataclass
class PipeItem:
    system_type: str = ""
    diameter: Optional[str] = None
    material: Optional[str] = None
    length: float = 0.0  # meters
    layer: Optional[str] = None
    entity_count: int = 1
    confidence: float = 1.0
    source: str = ""


@dataclass
class EquipmentItem:
    equipment_type: str = ""
    category: Optional[str] = None
    spec: Optional[str] = None
    count: int = 1
    unit: str = "个"
    layer: Optional[str] = None
    confidence: float = 1.0
    source: str = ""


@dataclass
class DimensionItem:
    value: str = ""
    numeric_value: Optional[float] = None
    position: Optional[Tuple[float, float, float]] = None
    dimension_type: Optional[str] = None
    layer: Optional[str] = None
    confidence: float = 1.0
    source: str = ""


@dataclass
class ExtractionResult:
    source: str = ""
    file_path: str = ""
    texts: List[TextItem] = field(default_factory=list)
    pipes: List[PipeItem] = field(default_factory=list)
    equipment: List[EquipmentItem] = field(default_factory=list)
    dimensions: List[DimensionItem] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    extraction_time: float = 0.0
    errors: List[str] = field(default_factory=list)
