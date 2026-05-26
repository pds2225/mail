"""CLOVA OCR API 클라이언트 (키 없으면 mock)."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import time

import httpx

log = logging.getLogger(__name__)

MOCK_PATH = Path(__file__).resolve().parent / "mock_ocr_result.json"
FORMAT_MAP = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
}


@dataclass
class OcrImageResult:
    name: str
    infer_result: str
    fields: list[dict]
    lines: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


class ClovaOcrClient:
    def __init__(
        self,
        ocr_url: str | None = None,
        ocr_secret: str | None = None,
        *,
        use_mock: bool | None = None,
    ) -> None:
        self.ocr_url = (ocr_url or os.environ.get("CLOVA_OCR_URL", "")).strip()
        self.ocr_secret = (ocr_secret or os.environ.get("CLOVA_OCR_SECRET", "")).strip()
        if use_mock is None:
            use_mock = not (self.ocr_url and self.ocr_secret)
        self.use_mock = use_mock
        if self.use_mock:
            log.info(
                "OCR 모드: Mock (테스트) - CLOVA_OCR_URL/SECRET 미설정, mock_ocr_result.json 사용"
            )
        else:
            log.info("OCR 모드: 실제 CLOVA OCR API")

    def recognize(self, file_path: Path) -> OcrImageResult:
        if self.use_mock:
            return self._recognize_mock(file_path)
        return self._recognize_api(file_path)

    def _recognize_mock(self, file_path: Path) -> OcrImageResult:
        with MOCK_PATH.open(encoding="utf-8") as f:
            payload = json.load(f)
        img = payload["images"][0]
        lines = [ln.get("inferText", "") for ln in img.get("lines", [])]
        return OcrImageResult(
            name=file_path.stem,
            infer_result=img.get("inferResult", "SUCCESS"),
            fields=img.get("fields", []),
            lines=lines,
            raw=payload,
        )

    def _recognize_api(self, file_path: Path) -> OcrImageResult:
        suffix = file_path.suffix.lower()
        fmt = FORMAT_MAP.get(suffix)
        if not fmt:
            raise ValueError(f"지원하지 않는 형식: {suffix}")

        image_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
        body = {
            "version": "V2",
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time() * 1000),
            "images": [
                {
                    "format": fmt,
                    "name": file_path.stem,
                    "data": image_b64,
                }
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "X-OCR-SECRET": self.ocr_secret,
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(self.ocr_url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()

        images = payload.get("images") or []
        if not images:
            raise RuntimeError("CLOVA OCR 응답에 images 없음")
        img = images[0]
        if img.get("inferResult") != "SUCCESS":
            raise RuntimeError(
                f"CLOVA OCR 실패: {img.get('message', img.get('inferResult'))}"
            )
        lines = [ln.get("inferText", "") for ln in img.get("lines", [])]
        return OcrImageResult(
            name=img.get("name", file_path.stem),
            infer_result=img.get("inferResult", ""),
            fields=img.get("fields", []),
            lines=lines,
            raw=payload,
        )
