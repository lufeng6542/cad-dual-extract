# -*- coding: utf-8 -*-
"""AI 视觉结果解析和标准化"""
import time
from typing import List
from cross_validation.schema import (
    TextItem, PipeItem, EquipmentItem, DimensionItem, ExtractionResult
)
from approach_b.vision_client import KimiVisionClient as ZhipuVisionClient
from approach_b.prompts import get_extraction_prompt


class VisionResultParser:
    def parse(self, raw: dict, source_image: str = "") -> ExtractionResult:
        result = ExtractionResult(source="approach_b")

        if "error" in raw:
            result.errors.append(f"AI返回错误: {raw['error']}")
            return result

        result.metadata = {
            "drawing_type": raw.get("drawing_type", ""),
            "scale": raw.get("scale", ""),
            "floor_info": raw.get("floor_info", ""),
        }

        # 文字
        for t in raw.get("texts", []):
            result.texts.append(TextItem(
                content=t.get("content", ""),
                text_type=t.get("type", "other"),
                confidence=0.8,
                source="approach_b"
            ))

        # 房间
        for r in raw.get("rooms", []):
            name = r.get("name", "")
            if name:
                result.texts.append(TextItem(
                    content=name, text_type="room_name",
                    confidence=0.75, source="approach_b"
                ))

        # 门窗编号
        for dw in raw.get("door_window_labels", []):
            code = dw.get("code", "")
            count = dw.get("count", 1)
            if code:
                result.equipment.append(EquipmentItem(
                    equipment_type=code, category="门窗",
                    count=count, unit="樘", confidence=0.7, source="approach_b"
                ))

        # 标注
        for d in raw.get("dimensions", []):
            result.dimensions.append(DimensionItem(
                value=str(d.get("value", "")),
                dimension_type="visual",
                confidence=0.7, source="approach_b"
            ))

        # 线段/墙体
        law = raw.get("lines_and_walls", {})
        wall_len = law.get("estimated_total_wall_length_m", 0)
        if wall_len > 0:
            result.pipes.append(PipeItem(
                system_type="墙体(视觉估计)", length=wall_len,
                confidence=0.5, source="approach_b"
            ))

        # 图块符号
        for b in raw.get("blocks_symbols", []):
            result.equipment.append(EquipmentItem(
                equipment_type=b.get("name", ""),
                category=b.get("category", "其他"),
                count=b.get("count", 1), unit="个",
                confidence=0.65, source="approach_b"
            ))

        return result

    def merge_tile_results(self, results: List[ExtractionResult]) -> ExtractionResult:
        if not results:
            return ExtractionResult(source="approach_b")
        if len(results) == 1:
            return results[0]

        merged = ExtractionResult(source="approach_b")
        merged.metadata = results[0].metadata

        # 合并文字（去重）
        seen_texts = set()
        for r in results:
            for t in r.texts:
                key = t.content.strip()
                if key not in seen_texts:
                    seen_texts.add(key)
                    merged.texts.append(t)

        # 合并设备（同类累加）
        equip_map = {}
        for r in results:
            for e in r.equipment:
                key = f"{e.equipment_type}|{e.category}"
                if key in equip_map:
                    equip_map[key].count += e.count
                else:
                    equip_map[key] = EquipmentItem(
                        equipment_type=e.equipment_type, category=e.category,
                        count=e.count, unit=e.unit, confidence=e.confidence,
                        source="approach_b"
                    )
        merged.equipment = list(equip_map.values())

        # 合并管道（同类累加）
        pipe_map = {}
        for r in results:
            for p in r.pipes:
                key = p.system_type
                if key in pipe_map:
                    pipe_map[key].length += p.length
                else:
                    pipe_map[key] = PipeItem(
                        system_type=p.system_type, length=p.length,
                        confidence=p.confidence, source="approach_b"
                    )
        merged.pipes = list(pipe_map.values())

        # 合并标注
        dim_set = set()
        for r in results:
            for d in r.dimensions:
                if d.value not in dim_set:
                    dim_set.add(d.value)
                    merged.dimensions.append(d)

        merged.errors = []
        for r in results:
            merged.errors.extend(r.errors)

        return merged


class VisionExtractor:
    def __init__(self, api_key: str = None):
        self.client = ZhipuVisionClient(api_key)
        self.parser = VisionResultParser()

    def extract_from_images(self, image_paths: List[str],
                            discipline: str = None) -> ExtractionResult:
        prompt = get_extraction_prompt(discipline)
        results = []

        for i, img_path in enumerate(image_paths):
            print(f"  AI分析图片 {i+1}/{len(image_paths)}: {img_path}")
            start = time.time()
            raw = self.client.analyze_image(img_path, prompt)
            elapsed = time.time() - start
            print(f"    耗时: {elapsed:.1f}s")

            if "error" in raw and "raw" not in raw:
                print(f"    错误: {raw['error']}")
                continue

            result = self.parser.parse(raw, img_path)
            result.extraction_time = elapsed
            results.append(result)

            # 打印部分结果
            n_texts = len(result.texts)
            n_equip = len(result.equipment)
            print(f"    提取: {n_texts}条文字, {n_equip}个设备")

        if len(results) > 1:
            return self.parser.merge_tile_results(results)
        elif results:
            return results[0]
        return ExtractionResult(source="approach_b", errors=["所有图片分析失败"])
