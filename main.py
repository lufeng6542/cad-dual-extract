# -*- coding: utf-8 -*-
"""
CAD 双方案提取 + 交叉验证系统

Usage:
  python main.py input.dxf
  python main.py input.dxf --skip-vision
  python main.py input.dxf --vision-only
  python main.py input.dxf --tile-dpi 200
"""
import argparse
import os
import sys
import time

# 修复 Windows mimetypes 注册表权限问题
import mimetypes
try:
    mimetypes.init()
except PermissionError:
    mimetypes._default_mime_types = mimetypes.MimeTypes()
    mimetypes._db = mimetypes._default_mime_types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from approach_a.extractor import EzdxfExtractor
from approach_b.renderer import DXFRenderer
from approach_b.result_parser import VisionExtractor
from cross_validation.validator import CrossValidator
from cross_validation.report_generator import ValidationReportGenerator


def main():
    parser = argparse.ArgumentParser(description="CAD双方案提取+交叉验证")
    parser.add_argument("input", help="输入DXF文件路径")
    parser.add_argument("--output", "-o", help="输出Excel路径（默认output/目录下）")
    parser.add_argument("--skip-vision", action="store_true", help="跳过方案B(AI视觉)")
    parser.add_argument("--vision-only", action="store_true", help="仅方案B(AI视觉)")
    parser.add_argument("--skip-dxf", action="store_true", help="跳过方案A(ezdxf)")
    parser.add_argument("--tile-dpi", type=int, default=150, help="渲染DPI(默认150)")
    parser.add_argument("--tile-max-px", type=int, default=2048*2048, help="单块最大像素")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"错误: 文件不存在 {args.input}")
        sys.exit(1)

    base_name = os.path.splitext(os.path.basename(args.input))[0]
    if args.output:
        output_path = args.output
    else:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{base_name}_验证报告.xlsx")

    print("=" * 60)
    print(f"  CAD 双方案提取 + 交叉验证")
    print(f"  输入: {args.input}")
    print(f"  输出: {output_path}")
    print("=" * 60)

    result_a = None
    result_b = None

    # ===== 方案A: ezdxf 直接解析 =====
    if not args.vision_only:
        print("\n[方案A] ezdxf 直接解析...")
        extractor_a = EzdxfExtractor()
        result_a = extractor_a.extract(args.input)
        print(f"  文字: {len(result_a.texts)} 条")
        print(f"  管道/线段: {len(result_a.pipes)} 组")
        print(f"  设备/图块: {len(result_a.equipment)} 种")
        print(f"  标注: {len(result_a.dimensions)} 个")
        print(f"  耗时: {result_a.extraction_time:.2f}s")

        if args.verbose:
            print("\n  --- 文字分类统计 ---")
            from collections import Counter
            types = Counter(t.text_type for t in result_a.texts)
            for t, c in types.most_common():
                print(f"    {t}: {c}")

            print("\n  --- 前10种图块 ---")
            for e in result_a.equipment[:10]:
                print(f"    {e.equipment_type}: x{e.count} ({e.category})")

    # ===== 方案B: AI 视觉识别 =====
    if not args.skip_dxf and not args.skip_vision:
        print("\n[方案B] 渲染图片 + AI视觉识别...")
        renderer = DXFRenderer(dpi=args.tile_dpi)
        images = renderer.render_full(args.input, max_pixels=args.tile_max_px)

        if images:
            print(f"  渲染完成: {len(images)} 张图片")
            vision_ext = VisionExtractor()
            result_b = vision_ext.extract_from_images(images)
            print(f"  文字: {len(result_b.texts)} 条")
            print(f"  管道: {len(result_b.pipes)} 组")
            print(f"  设备: {len(result_b.equipment)} 种")
            print(f"  标注: {len(result_b.dimensions)} 个")
            print(f"  耗时: {result_b.extraction_time:.2f}s")
        else:
            print("  渲染失败，跳过方案B")

    # ===== 交叉验证 =====
    if result_a and result_b:
        print("\n[交叉验证] 比对两方案结果...")
        validator = CrossValidator()
        validation = validator.validate(result_a, result_b)

        s = validation["summary"]
        print(f"\n  文字: A={s['texts']['a_count']} B={s['texts']['b_count']} "
              f"匹配={s['texts']['matched']} 仅A={s['texts']['a_only']} 仅B={s['texts']['b_only']}")
        print(f"  管道: A={s['pipes']['a_count']} B={s['pipes']['b_count']} "
              f"匹配={s['pipes']['matched']} 差异={s['pipes']['discrepancies']}")
        print(f"  设备: A={s['equipment']['a_count']} B={s['equipment']['b_count']} "
              f"匹配={s['equipment']['matched']} 差异={s['equipment']['discrepancies']}")
        print(f"  标注: A={s['dimensions']['a_count']} B={s['dimensions']['b_count']} "
              f"匹配={s['dimensions']['matched']}")
        print(f"  需人工复核: {len(validation['review_items'])} 项")

        # 生成报告
        report_gen = ValidationReportGenerator()
        report_gen.generate(validation, result_a, result_b, output_path)

    elif result_a:
        print("\n[仅方案A] 无方案B结果，跳过交叉验证")
        # 仍然输出方案A的结果摘要
        wb_path = output_path.replace('.xlsx', '_方案A.xlsx')
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "方案A结果"
        ws.append(["类型", "名称", "值", "图层"])
        for t in result_a.texts:
            ws.append(["文字", t.content[:80], t.text_type, t.layer])
        for p in result_a.pipes:
            ws.append(["管道", p.system_type, f"{p.length}m", p.layer])
        for e in result_a.equipment:
            ws.append(["设备", e.equipment_type, f"x{e.count}", e.layer])
        for d in result_a.dimensions:
            ws.append(["标注", d.value, d.numeric_value, d.layer])
        wb.save(wb_path)
        print(f"方案A结果已保存: {wb_path}")

    print("\n" + "=" * 60)
    print("  完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
