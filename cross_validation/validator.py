# -*- coding: utf-8 -*-
"""交叉验证引擎"""
from difflib import SequenceMatcher
from collections import defaultdict
from typing import List, Dict, Tuple
from cross_validation.schema import (
    TextItem, PipeItem, EquipmentItem, DimensionItem, ExtractionResult
)


class TextComparator:
    def __init__(self, fuzzy_threshold: float = 0.75):
        self.fuzzy_threshold = fuzzy_threshold

    def compare(self, texts_a: List[TextItem],
                texts_b: List[TextItem]) -> Dict:
        matched = []
        a_only = list(texts_a)
        b_only = list(texts_b)

        for ta in list(a_only):
            best_match = None
            best_sim = 0
            for tb in b_only:
                sim = self._similarity(ta.content, tb.content)
                if sim > best_sim:
                    best_sim = sim
                    best_match = tb

            if best_match and best_sim >= self.fuzzy_threshold:
                matched.append({
                    "item_a": ta, "item_b": best_match,
                    "match_type": "exact" if best_sim >= 0.95 else "fuzzy",
                    "similarity": round(best_sim, 3)
                })
                a_only.remove(ta)
                b_only.remove(best_match)

        return {"matched": matched, "a_only": a_only, "b_only": b_only}

    def _similarity(self, a: str, b: str) -> float:
        a_norm = a.strip().replace(' ', '').upper()
        b_norm = b.strip().replace(' ', '').upper()
        if a_norm == b_norm:
            return 1.0
        return SequenceMatcher(None, a_norm, b_norm).ratio()


class QuantityComparator:
    def __init__(self, length_tolerance: float = 0.10, count_tolerance: int = 0):
        self.length_tolerance = length_tolerance
        self.count_tolerance = count_tolerance

    def compare_pipes(self, pipes_a: List[PipeItem],
                      pipes_b: List[PipeItem]) -> Dict:
        matched, discrepancies, a_only, b_only = [], [], list(pipes_a), list(pipes_b)

        for pa in list(a_only):
            best_match = None
            best_dev = float('inf')
            for pb in b_only:
                if not pa.system_type and not pb.system_type:
                    continue
                dev = self._deviation(pa.length, pb.length)
                if dev < best_dev:
                    best_dev = dev
                    best_match = pb

            if best_match:
                if best_dev <= self.length_tolerance:
                    matched.append({
                        "item_a": pa, "item_b": best_match,
                        "deviation_pct": round(best_dev * 100, 1),
                        "status": "一致"
                    })
                else:
                    discrepancies.append({
                        "item_a": pa, "item_b": best_match,
                        "deviation_pct": round(best_dev * 100, 1),
                        "status": "偏差超标"
                    })
                a_only.remove(pa)
                b_only.remove(best_match)

        return {"matched": matched, "discrepancies": discrepancies,
                "a_only": a_only, "b_only": b_only}

    def compare_equipment(self, equip_a: List[EquipmentItem],
                          equip_b: List[EquipmentItem]) -> Dict:
        matched, discrepancies, a_only, b_only = [], [], list(equip_a), list(equip_b)

        for ea in list(a_only):
            best_match = None
            best_sim = 0
            for eb in b_only:
                sim = SequenceMatcher(None,
                                      ea.equipment_type.lower(),
                                      eb.equipment_type.lower()).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_match = eb

            if best_match and best_sim >= 0.6:
                count_diff = abs(ea.count - eb.count)
                if count_diff <= self.count_tolerance:
                    matched.append({
                        "item_a": ea, "item_b": best_match,
                        "name_similarity": round(best_sim, 3),
                        "status": "一致"
                    })
                else:
                    discrepancies.append({
                        "item_a": ea, "item_b": best_match,
                        "name_similarity": round(best_sim, 3),
                        "count_diff": count_diff,
                        "status": f"数量差异(A={ea.count}, B={best_match.count})"
                    })
                a_only.remove(ea)
                b_only.remove(best_match)

        return {"matched": matched, "discrepancies": discrepancies,
                "a_only": a_only, "b_only": b_only}

    def compare_dimensions(self, dims_a: List[DimensionItem],
                           dims_b: List[DimensionItem]) -> Dict:
        matched, a_only, b_only = [], list(dims_a), list(dims_b)

        for da in list(a_only):
            for db in list(b_only):
                try:
                    va = float(da.value.replace('mm', '').replace('m', '').strip())
                    vb = float(db.value.replace('mm', '').replace('m', '').strip())
                    dev = self._deviation(va, vb)
                    if dev <= 0.05:
                        matched.append({
                            "item_a": da, "item_b": db,
                            "deviation_pct": round(dev * 100, 1)
                        })
                        a_only.remove(da)
                        b_only.remove(db)
                        break
                except ValueError:
                    if da.value.strip() == db.value.strip():
                        matched.append({
                            "item_a": da, "item_b": db, "deviation_pct": 0
                        })
                        a_only.remove(da)
                        b_only.remove(db)
                        break

        return {"matched": matched, "a_only": a_only, "b_only": b_only}

    def _deviation(self, a: float, b: float) -> float:
        if a == 0 and b == 0:
            return 0
        return abs(a - b) / max(abs(a), abs(b))


class CrossValidator:
    def __init__(self):
        self.text_comp = TextComparator()
        self.qty_comp = QuantityComparator()

    def validate(self, result_a: ExtractionResult,
                 result_b: ExtractionResult) -> Dict:
        text_result = self.text_comp.compare(result_a.texts, result_b.texts)
        pipe_result = self.qty_comp.compare_pipes(result_a.pipes, result_b.pipes)
        equip_result = self.qty_comp.compare_equipment(
            result_a.equipment, result_b.equipment)
        dim_result = self.qty_comp.compare_dimensions(
            result_a.dimensions, result_b.dimensions)

        # 统计
        summary = {
            "texts": {
                "a_count": len(result_a.texts), "b_count": len(result_b.texts),
                "matched": len(text_result["matched"]),
                "a_only": len(text_result["a_only"]),
                "b_only": len(text_result["b_only"]),
            },
            "pipes": {
                "a_count": len(result_a.pipes), "b_count": len(result_b.pipes),
                "matched": len(pipe_result["matched"]),
                "discrepancies": len(pipe_result["discrepancies"]),
            },
            "equipment": {
                "a_count": len(result_a.equipment), "b_count": len(result_b.equipment),
                "matched": len(equip_result["matched"]),
                "discrepancies": len(equip_result["discrepancies"]),
            },
            "dimensions": {
                "a_count": len(result_a.dimensions), "b_count": len(result_b.dimensions),
                "matched": len(dim_result["matched"]),
            },
            "time_a": result_a.extraction_time,
            "time_b": result_b.extraction_time,
        }

        # 需要人工复核的项目
        review_items = []
        for d in pipe_result.get("discrepancies", []):
            review_items.append({
                "category": "管道", "key": d["item_a"].system_type,
                "value_a": d["item_a"].length, "value_b": d["item_b"].length,
                "deviation": d["deviation_pct"], "confidence": 0.3
            })
        for d in equip_result.get("discrepancies", []):
            review_items.append({
                "category": "设备", "key": d["item_a"].equipment_type,
                "value_a": d["item_a"].count, "value_b": d["item_b"].count,
                "deviation": "数量差异", "confidence": 0.3
            })

        return {
            "text": text_result,
            "pipe": pipe_result,
            "equipment": equip_result,
            "dimension": dim_result,
            "summary": summary,
            "review_items": review_items
        }
