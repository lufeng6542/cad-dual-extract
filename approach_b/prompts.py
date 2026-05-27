# -*- coding: utf-8 -*-
"""结构化提取 Prompt"""


EXTRACTION_PROMPT = """你是一名专业的建筑工程图纸识读专家。请仔细分析这张CAD图纸渲染图，提取以下信息。

请严格按照JSON格式返回，不要包含任何其他文字：

{
  "drawing_type": "图纸类型（如：建筑平面图、结构平面图、立面图等）",
  "scale": "比例尺（如1:100），看不出来写unknown",
  "floor_info": "楼层信息（如：一层平面图、屋顶平面图），看不出来写unknown",
  "texts": [
    {"content": "文字内容", "type": "room_name|label|dimension|elevation|other", "estimated_area": "左上|右上|左下|右下|中间"}
  ],
  "rooms": [
    {"name": "房间名称", "estimated_area_m2": 0}
  ],
  "door_window_labels": [
    {"code": "门窗编号", "count": 1}
  ],
  "dimensions": [
    {"value": "标注值", "unit": "mm或m"}
  ],
  "lines_and_walls": {
    "estimated_total_wall_length_m": 0,
    "major_wall_layers_visible": ["图层名"]
  },
  "blocks_symbols": [
    {"name": "图块/符号描述", "count": 1, "category": "门窗|柱|楼梯|电梯|卫浴|标注|其他"}
  ]
}

注意：
1. 只提取图中能明确识别的内容，不确定的不要编造
2. 文字内容要精确，不要修改原文
3. 数量尽量准确
4. 面积和长度是估计值即可"""


def get_extraction_prompt(discipline: str = None) -> str:
    return EXTRACTION_PROMPT
