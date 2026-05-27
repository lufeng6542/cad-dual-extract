# -*- coding: utf-8 -*-
"""方案A: ezdxf 直接解析提取器"""
import ezdxf
import math
import re
import time
import sys
from collections import Counter, defaultdict
from cross_validation.schema import (
    TextItem, PipeItem, EquipmentItem, DimensionItem, ExtractionResult
)


class EzdxfExtractor:
    def __init__(self):
        self.room_kws = ['室', '厅', '房', '间', '廊', '台', '梯', '厨', '卫',
                         '库', '棚', '井', '坑', '道', '沟']
        self.arch_kws = ['平面', '立面', '剖面', '大样', '楼梯', '卫生间', '厨房',
                         '卧室', '客厅', '阳台', '走廊', '门厅', '电梯', '机房',
                         '图名', '比例', '标高', '层高', '轴线', '门窗', '建施',
                         '结施', '说明', '防火', '疏散', '层数', '高度', '面积',
                         '门窗表', '做法', '墙体', '楼面', '屋面', '散水', '女儿墙']

    def extract(self, dxf_path: str) -> ExtractionResult:
        start = time.time()
        result = ExtractionResult(source="approach_a", file_path=dxf_path)

        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            result.errors.append(f"读取失败: {e}")
            return result

        msp = doc.modelspace()

        # 基本元数据
        result.metadata = {
            "dxf_version": doc.dxfversion,
            "encoding": doc.encoding,
            "layouts": [l.name for l in doc.layouts],
        }

        # 提取各类实体
        result.texts = self._extract_texts(msp)
        result.dimensions = self._extract_dimensions(msp)
        result.pipes = self._extract_lines(msp)
        result.equipment = self._extract_blocks(msp)

        result.extraction_time = time.time() - start
        return result

    def _extract_texts(self, msp) -> list:
        texts = []
        for entity in msp.query('TEXT MTEXT'):
            etype = entity.dxftype()
            layer = entity.dxf.layer

            try:
                pos = (entity.dxf.insert.x, entity.dxf.insert.y, 0)
            except:
                pos = None

            if etype == 'TEXT':
                content = str(entity.dxf.text or "").strip()
                try:
                    height = entity.dxf.height
                except:
                    height = 0
            else:
                content = str(entity.text or "").strip()
                try:
                    height = entity.dxf.char_height
                except:
                    height = 0

            content = content.replace('\P', ' ').replace('\n', ' ').strip()
            if not content:
                continue

            # 分类文字
            text_type = self._classify_text(content)
            texts.append(TextItem(
                content=content, position=pos, layer=layer,
                height=height, text_type=text_type, source="approach_a"
            ))
        return texts

    def _classify_text(self, text: str) -> str:
        if any(kw in text for kw in self.room_kws) and 2 <= len(text) <= 15:
            return "room_name"
        if re.match(r'^[A-Z]{1,3}\d{3,5}[A-Z]*$', text.upper()):
            return "door_window_code"
        if re.search(r'DN\d+|De\d+|Φ\d+|φ\d+', text):
            return "pipe_label"
        if re.match(r'^[+-]?\d+\.\d+$', text) or '标高' in text:
            return "elevation"
        if re.search(r'\d+:\d+', text):
            return "scale"
        if any(kw in text for kw in self.arch_kws):
            return "arch_keyword"
        if any(x in text for x in ['m²', 'M2', 'm2', '㎡', '面积']):
            return "area"
        return "other"

    def _extract_dimensions(self, msp) -> list:
        dims = []
        for entity in msp.query('DIMENSION'):
            dim_type = entity.dxf.dimtype if hasattr(entity.dxf, 'dimtype') else -1
            try:
                measurement = entity.get_measurement()
                if measurement is not None:
                    numeric = abs(measurement)
                    value_str = f"{numeric:.0f}" if numeric >= 1 else f"{numeric:.2f}"
                    dims.append(DimensionItem(
                        value=value_str, numeric_value=numeric,
                        dimension_type=self._dim_type_name(dim_type),
                        layer=entity.dxf.layer if hasattr(entity.dxf, 'layer') else None,
                        source="approach_a"
                    ))
            except:
                pass
            try:
                text = entity.dxf.text
                if text and text != '<>' and text not in [d.value for d in dims]:
                    dims.append(DimensionItem(
                        value=text, dimension_type=self._dim_type_name(dim_type),
                        layer=entity.dxf.layer if hasattr(entity.dxf, 'layer') else None,
                        source="approach_a"
                    ))
            except:
                pass
        return dims

    def _dim_type_name(self, dimtype: int) -> str:
        names = {0: '线性', 1: '对齐', 2: '角度', 3: '直径', 4: '半径',
                 5: '三点角度', 6: '坐标'}
        return names.get(dimtype, f'类型{dimtype}')

    def _extract_lines(self, msp) -> list:
        lines_by_layer = defaultdict(lambda: {"count": 0, "total_length": 0})

        for entity in msp:
            etype = entity.dxftype()
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'

            if etype == 'LINE':
                try:
                    start = entity.dxf.start
                    end = entity.dxf.end
                    length = math.sqrt((end.x - start.x)**2 + (end.y - start.y)**2)
                    lines_by_layer[layer]["count"] += 1
                    lines_by_layer[layer]["total_length"] += length
                except:
                    pass
            elif etype == 'LWPOLYLINE':
                try:
                    length = entity.length
                    lines_by_layer[layer]["count"] += 1
                    lines_by_layer[layer]["total_length"] += length
                except:
                    pass
            elif etype == 'ARC':
                try:
                    length = entity.arc_length
                    lines_by_layer[layer]["count"] += 1
                    lines_by_layer[layer]["total_length"] += length
                except:
                    pass

        pipes = []
        for layer, data in sorted(lines_by_layer.items(),
                                   key=lambda x: x[1]["total_length"], reverse=True):
            if data["total_length"] > 0:
                pipes.append(PipeItem(
                    system_type=layer, length=round(data["total_length"] / 1000, 2),
                    entity_count=data["count"], layer=layer, source="approach_a"
                ))
        return pipes

    def _extract_blocks(self, msp) -> list:
        block_counter = Counter()
        block_layers = defaultdict(set)

        for entity in msp.query('INSERT'):
            name = entity.dxf.name
            block_counter[name] += 1
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0'
            block_layers[name].add(layer)

        equipment = []
        for name, count in block_counter.most_common():
            layers = ', '.join(sorted(block_layers[name]))
            category = self._classify_block(name)
            equipment.append(EquipmentItem(
                equipment_type=name, category=category,
                count=count, unit="个", layer=layers, source="approach_a"
            ))
        return equipment

    def _classify_block(self, name: str) -> str:
        name_lower = name.lower()
        if any(kw in name_lower for kw in ['door', 'win', 'gc', 'lm', 'fm', '门', '窗']):
            return "门窗"
        if any(kw in name_lower for kw in ['column', 'col', '柱']):
            return "柱"
        if any(kw in name_lower for kw in ['stair', '梯']):
            return "楼梯"
        if any(kw in name_lower for kw in ['elev', 'lvtr', 'evtr', '电梯']):
            return "电梯"
        if any(kw in name_lower for kw in ['dim', '标注']):
            return "标注"
        if any(kw in name_lower for kw in ['text', '文字']):
            return "文字"
        if any(kw in name_lower for kw in ['axis', '轴']):
            return "轴网"
        return "其他"
