# -*- coding: utf-8 -*-
"""AI 视觉识别客户端 — Kimi moonshot-v1-vision (原智谱 → 已迁移)"""
import base64
import json
import os
import requests
from typing import Optional


class KimiVisionClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or self._load_api_key()
        self.base_url = "https://api.moonshot.cn/v1/chat/completions"

    def _load_api_key(self) -> str:
        env_path = os.path.expanduser("~/.baoyu-skills/.env")
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('KIMI_API_KEY='):
                        return line.split('=', 1)[1].strip().strip('"').strip("'")
        return os.environ.get('KIMI_API_KEY', '')

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def analyze_image(self, image_path: str, prompt: str) -> dict:
        b64 = self._encode_image(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(ext, 'image/png')

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "moonshot-v1-8k-vision-preview",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                ]
            }],
            "temperature": 0.1,
            "max_tokens": 4096
        }

        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return self._parse_json_response(text)
        except Exception as e:
            return {"error": str(e), "raw": ""}

    def _parse_json_response(self, text: str) -> dict:
        text = text.strip()
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except:
            return {"error": "JSON解析失败", "raw": text}


# 向后兼容别名
ZhipuVisionClient = KimiVisionClient
