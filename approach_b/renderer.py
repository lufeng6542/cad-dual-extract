# -*- coding: utf-8 -*-
"""DXF 渲染为图片 + 分块"""
import ezdxf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import os
import math
from typing import List, Dict, Optional


class DXFRenderer:
    def __init__(self, dpi: int = 150, font: str = 'SimHei'):
        self.dpi = dpi
        self.font = font
        plt.rcParams['font.sans-serif'] = [font, 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

    def _extents_from_header(self, doc) -> Optional[Dict]:
        """从 DXF header 的 $EXTMIN/$EXTMAX 获取图纸范围"""
        try:
            extmin = doc.header.get('$EXTMIN')
            extmax = doc.header.get('$EXTMAX')
            if extmin and extmax:
                w = extmax.x - extmin.x
                h = extmax.y - extmin.y
                if w > 0 and h > 0:
                    return {
                        "min_x": extmin.x, "min_y": extmin.y,
                        "max_x": extmax.x, "max_y": extmax.y,
                        "width": w, "height": h
                    }
        except Exception:
            pass
        return None

    def _extents_from_entities(self, msp) -> Optional[Dict]:
        """从 LINE/POINT/LWPOLYLINE 等实体直接提取坐标"""
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        count = 0
        for entity in msp:
            try:
                etype = entity.dxftype()
                if etype == 'LINE':
                    coords = [(entity.dxf.start.x, entity.dxf.start.y),
                               (entity.dxf.end.x, entity.dxf.end.y)]
                elif etype == 'POINT':
                    coords = [(entity.dxf.location.x, entity.dxf.location.y)]
                elif etype == 'CIRCLE':
                    c, r = (entity.dxf.center.x, entity.dxf.center.y), entity.dxf.radius
                    coords = [(c[0]-r, c[1]-r), (c[0]+r, c[1]+r)]
                elif etype == 'ARC':
                    import math as _m
                    c = (entity.dxf.center.x, entity.dxf.center.y)
                    r = entity.dxf.radius
                    coords = [(c[0]-r, c[1]-r), (c[0]+r, c[1]+r)]
                elif etype == 'LWPOLYLINE':
                    coords = [(p[0], p[1]) for p in entity.get_points(format='xy')]
                elif etype in ('TEXT', 'MTEXT'):
                    coords = [(entity.dxf.insert.x, entity.dxf.insert.y)]
                else:
                    bb = entity.bounding_box()
                    if bb.has_data:
                        coords = [(bb.extmin.x, bb.extmin.y),
                                   (bb.extmax.x, bb.extmax.y)]
                    else:
                        continue
                for x, y in coords:
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
                count += 1
            except Exception:
                pass
        if count == 0 or min_x == float('inf'):
            return None
        return {
            "min_x": min_x, "min_y": min_y,
            "max_x": max_x, "max_y": max_y,
            "width": max_x - min_x, "height": max_y - min_y
        }

    def get_extents(self, msp, doc=None) -> Dict[str, float]:
        # 策略1: 从 header 取
        if doc:
            result = self._extents_from_header(doc)
            if result:
                return result
        # 策略2: 从实体坐标直接取
        result = self._extents_from_entities(msp)
        if result:
            return result
        # 策略3: 原始 bounding_box 方式
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        count = 0
        for entity in msp:
            try:
                bb = entity.bounding_box()
                if bb.has_data:
                    min_x = min(min_x, bb.extmin.x)
                    min_y = min(min_y, bb.extmin.y)
                    max_x = max(max_x, bb.extmax.x)
                    max_y = max(max_y, bb.extmax.y)
                    count += 1
            except:
                pass
        if min_x == float('inf') or count == 0:
            return {"width": 0, "height": 0}
        return {
            "min_x": min_x, "min_y": min_y,
            "max_x": max_x, "max_y": max_y,
            "width": max_x - min_x, "height": max_y - min_y
        }

    def calculate_tiles(self, extents: Dict, max_pixels: int = 2048*2048,
                        overlap: float = 0.1, max_tiles: int = 64,
                        tile_figsize: float = 20.0) -> List[Dict]:
        if extents["width"] == 0:
            return []

        # 每个 tile 覆盖的像素: figsize * dpi per side
        tile_px = tile_figsize * self.dpi
        tile_total_px = tile_px * tile_px
        # 总像素 = 图纸宽高比 * tile面积 * 需要多少个tile
        n_tiles_w = math.ceil(extents["width"] / (tile_px / self.dpi * 25.4))
        n_tiles_h = math.ceil(extents["height"] / (tile_px / self.dpi * 25.4))

        # 简化：按图纸面积和目标 tile 像素面积算
        total_area = extents["width"] * extents["height"]
        # 每个 tile 覆盖的 DXF 单位面积（假设 20inch * dpi 个像素对应的 DXF 范围）
        # 更直接：每个 tile 的像素数 = figsize * dpi 的平方
        # 我们需要让每个 tile 的像素数 <= max_pixels
        # 但我们不知道 DXF 单位到像素的映射，因为 render_tile 用的是 set_xlim 直接设 DXF 坐标
        # 实际像素由 figsize * dpi 决定，而 DXF 坐标通过 set_xlim 映射
        # 所以一个 tile 的像素数 = figsize * dpi 在每条边上
        # 我们的目标：每个 tile 的 DXF 范围不要太大，让细节可见
        # 目标每个 tile 覆盖 ~50000 DXF 单位宽度（约适合 A0 图纸的一个区域）
        target_tile_dxf_width = 150000
        cols = max(1, math.ceil(extents["width"] / target_tile_dxf_width))
        rows = max(1, math.ceil(extents["height"] / target_tile_dxf_width))
        total = cols * rows
        if total > max_tiles:
            scale = math.sqrt(max_tiles / total)
            cols = max(1, round(cols * scale))
            rows = max(1, round(rows * scale))
            total = cols * rows

        tile_w = extents["width"] / cols
        tile_h = extents["height"] / rows
        overlap_w = tile_w * overlap
        overlap_h = tile_h * overlap

        tiles = []
        for r in range(rows):
            for c in range(cols):
                x0 = extents["min_x"] + c * tile_w - overlap_w
                y0 = extents["min_y"] + r * tile_h - overlap_h
                x1 = x0 + tile_w + 2 * overlap_w
                y1 = y0 + tile_h + 2 * overlap_h
                tiles.append({
                    "min_x": x0, "min_y": y0,
                    "max_x": x1, "max_y": y1,
                    "tile_id": r * cols + c,
                    "row": r, "col": c
                })
        return tiles

    def render_tile(self, msp, tile: Dict, output_path: str) -> Optional[str]:
        from ezdxf.addons.drawing import RenderContext, Frontend
        from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

        try:
            fig, ax = plt.subplots(1, 1, figsize=(20, 20), dpi=self.dpi)
            ax.set_xlim(tile["min_x"], tile["max_x"])
            ax.set_ylim(tile["min_y"], tile["max_y"])
            ax.set_aspect('equal')
            ax.set_facecolor('white')
            fig.patch.set_facecolor('white')

            ctx = RenderContext(msp.doc)
            out = MatplotlibBackend(ax)
            Frontend(ctx, out).draw_layout(msp)

            plt.tight_layout(pad=0)
            fig.savefig(output_path, dpi=self.dpi, bbox_inches='tight',
                        facecolor='white', edgecolor='none')
            plt.close(fig)
            return output_path
        except Exception as e:
            print(f"  渲染失败 tile {tile['tile_id']}: {e}")
            plt.close('all')
            return None

    def render_full(self, dxf_path: str, output_dir: str = None,
                    max_pixels: int = 2048*2048) -> List[str]:
        if output_dir is None:
            output_dir = os.path.dirname(dxf_path)

        base_name = os.path.splitext(os.path.basename(dxf_path))[0]
        render_dir = os.path.join(output_dir, f"{base_name}_tiles")
        os.makedirs(render_dir, exist_ok=True)

        print(f"  加载 DXF: {dxf_path}")
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()

        extents = self.get_extents(msp, doc=doc)
        print(f"  图纸范围: {extents['width']:.0f} x {extents['height']:.0f}")

        tiles = self.calculate_tiles(extents, max_pixels)
        print(f"  分块数量: {len(tiles)}")

        images = []
        for i, tile in enumerate(tiles):
            out_path = os.path.join(render_dir, f"tile_{tile['tile_id']:03d}.png")
            print(f"  渲染 tile {i+1}/{len(tiles)}...", end="", flush=True)
            result = self.render_tile(msp, tile, out_path)
            if result:
                images.append(result)
                print(" 完成")
            else:
                print(" 失败")

        return images
