from __future__ import annotations

import base64
import io
import json
from typing import Any

from .models import Attachment, AttachmentModality, MultimodalFinding

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


VISION_PROMPT = (
    "你是一个网约车安全多模态分析助手。"
    "请分析图片中的文字、场景和安全线索，并返回 JSON，包含以下字段："
    "summary、extracted_text、signals、evidence_candidates。"
    "所有自然语言内容请使用简体中文。signals 使用英文短标签。"
)


class MultimodalAnalyzer:
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        vision_model: str,
        audio_model: str,
        fallback_model: str,
    ) -> None:
        self.vision_model = vision_model
        self.audio_model = audio_model
        self.fallback_model = fallback_model
        self.client = None
        self._last_debug: list[dict[str, Any]] = []
        if api_key and OpenAI is not None:
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self.client = OpenAI(**client_kwargs)

    def analyze_attachments(self, attachments: list[Attachment]) -> list[MultimodalFinding]:
        self._last_debug = []
        findings: list[MultimodalFinding] = []
        for attachment in attachments:
            findings.extend(self._analyze_attachment(attachment))
        return findings

    def get_last_debug(self) -> list[dict[str, Any]]:
        return list(self._last_debug)

    def _analyze_attachment(self, attachment: Attachment) -> list[MultimodalFinding]:
        if attachment.modality == AttachmentModality.text:
            if attachment.content:
                self._last_debug.append(
                    {
                        "task": "multimodal_parse",
                        "mode": "heuristic_only",
                        "model": self.fallback_model,
                        "client_available": self.client is not None,
                        "system_prompt": "纯文本附件不需要调用多模态模型，直接并入案件上下文。",
                        "user_payload": {"modality": "text", "file_name": attachment.file_name},
                        "raw_response": attachment.content,
                        "parsed_response": {"text": attachment.content},
                        "error": None,
                    }
                )
                return [
                    MultimodalFinding(
                        modality=attachment.modality,
                        source="text_attachment",
                        text=attachment.content,
                        summary="已直接使用文本附件内容。",
                        extracted_text=attachment.content,
                        model_used=None,
                        file_name=attachment.file_name,
                    )
                ]
            return []

        if attachment.modality == AttachmentModality.image:
            return [self._analyze_image(attachment)]

        if attachment.modality == AttachmentModality.audio:
            return [self._analyze_audio(attachment)]

        return []

    def _analyze_image(self, attachment: Attachment) -> MultimodalFinding:
        if attachment.ocr_text:
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "heuristic_only",
                    "model": self.vision_model,
                    "client_available": self.client is not None,
                    "system_prompt": "已提供 OCR 文本，直接使用，无需再次调用视觉模型。",
                    "user_payload": {"modality": "image", "file_name": attachment.file_name},
                    "raw_response": attachment.ocr_text,
                    "parsed_response": {"text": attachment.ocr_text},
                    "error": None,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="provided_ocr",
                text=f"图片 OCR：{attachment.ocr_text}",
                summary="已直接使用提供的 OCR 文本。",
                extracted_text=attachment.ocr_text,
                model_used=None,
                file_name=attachment.file_name,
            )

        if self.client is None or not (attachment.media_base64 or attachment.media_url):
            error = "缺少可用的图片原始媒体或未配置多模态 client，无法调用视觉模型。"
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "heuristic_only",
                    "model": self.vision_model,
                    "client_available": self.client is not None,
                    "system_prompt": VISION_PROMPT,
                    "user_payload": {"modality": "image", "file_name": attachment.file_name},
                    "raw_response": None,
                    "parsed_response": None,
                    "error": error,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="image_fallback",
                text="",
                summary="图片未提供可直接使用的 OCR 文本，也未成功走视觉解析。",
                extracted_text=None,
                model_used=None,
                file_name=attachment.file_name,
                error=error,
            )

        image_url = attachment.media_url or self._data_url(attachment.media_base64 or "", attachment.mime_type or "image/png")
        payload = {
            "modality": "image",
            "file_name": attachment.file_name,
            "mime_type": attachment.mime_type,
        }
        try:
            response = self.client.chat.completions.create(
                model=self.vision_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "请抽取图片中的可见文字、场景摘要和可能的安全风险信号。"
                                    "如果图片中没有明确安全线索，也请诚实说明。"
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            )
            raw_response = response.choices[0].message.content or "{}"
            parsed = json.loads(raw_response)
            summary = str(parsed.get("summary", "") or "")
            extracted_text = str(parsed.get("extracted_text", "") or "")
            evidence_candidates = [str(item) for item in parsed.get("evidence_candidates", [])]
            text = " | ".join(item for item in [f"图片摘要：{summary}" if summary else "", f"图片识别文本：{extracted_text}" if extracted_text else ""] + evidence_candidates if item)
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "llm_success",
                    "model": self.vision_model,
                    "client_available": self.client is not None,
                    "system_prompt": VISION_PROMPT,
                    "user_payload": payload,
                    "raw_response": raw_response,
                    "parsed_response": parsed,
                    "error": None,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="vision_api",
                text=text,
                summary=summary or "已完成图片内容解析。",
                extracted_text=extracted_text or None,
                signals=[str(item) for item in parsed.get("signals", [])],
                model_used=self.vision_model,
                file_name=attachment.file_name,
            )
        except Exception as exc:
            error = f"视觉模型解析失败：{exc}"
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "llm_fallback",
                    "model": self.vision_model,
                    "client_available": self.client is not None,
                    "system_prompt": VISION_PROMPT,
                    "user_payload": payload,
                    "raw_response": None,
                    "parsed_response": None,
                    "error": error,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="vision_fallback",
                text="",
                summary="图片解析失败，已跳过多模态增强。",
                extracted_text=None,
                model_used=self.vision_model,
                file_name=attachment.file_name,
                error=error,
            )

    def _analyze_audio(self, attachment: Attachment) -> MultimodalFinding:
        if attachment.transcript:
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "heuristic_only",
                    "model": self.audio_model,
                    "client_available": self.client is not None,
                    "system_prompt": "已提供 ASR 文本，直接使用，无需再次调用音频模型。",
                    "user_payload": {"modality": "audio", "file_name": attachment.file_name},
                    "raw_response": attachment.transcript,
                    "parsed_response": {"text": attachment.transcript},
                    "error": None,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="provided_transcript",
                text=f"音频转写：{attachment.transcript}",
                summary="已直接使用提供的音频转写文本。",
                extracted_text=attachment.transcript,
                model_used=None,
                file_name=attachment.file_name,
            )

        if self.client is None or not attachment.media_base64:
            error = "缺少可用的音频原始媒体或未配置多模态 client，无法调用音频模型。"
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "heuristic_only",
                    "model": self.audio_model,
                    "client_available": self.client is not None,
                    "system_prompt": "音频将优先做 transcription，再并入文本工作流。",
                    "user_payload": {"modality": "audio", "file_name": attachment.file_name},
                    "raw_response": None,
                    "parsed_response": None,
                    "error": error,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="audio_fallback",
                text="",
                summary="音频未提供转写文本，也未成功走音频模型。",
                extracted_text=None,
                model_used=None,
                file_name=attachment.file_name,
                error=error,
            )

        payload = {"modality": "audio", "file_name": attachment.file_name, "mime_type": attachment.mime_type}
        try:
            audio_bytes = base64.b64decode(attachment.media_base64)
            buffer = io.BytesIO(audio_bytes)
            buffer.name = attachment.file_name or "attachment.wav"
            response = self.client.audio.transcriptions.create(model=self.audio_model, file=buffer)
            transcript = str(getattr(response, "text", "") or "")
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "llm_success",
                    "model": self.audio_model,
                    "client_available": self.client is not None,
                    "system_prompt": "将音频内容转写为文本，再交给文本工作流处理。",
                    "user_payload": payload,
                    "raw_response": transcript,
                    "parsed_response": {"text": transcript},
                    "error": None,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="audio_api",
                text=f"音频转写：{transcript}",
                summary="已通过音频模型完成转写。",
                extracted_text=transcript or None,
                model_used=self.audio_model,
                file_name=attachment.file_name,
            )
        except Exception as exc:
            error = f"音频模型解析失败：{exc}"
            self._last_debug.append(
                {
                    "task": "multimodal_parse",
                    "mode": "llm_fallback",
                    "model": self.audio_model,
                    "client_available": self.client is not None,
                    "system_prompt": "将音频内容转写为文本，再交给文本工作流处理。",
                    "user_payload": payload,
                    "raw_response": None,
                    "parsed_response": None,
                    "error": error,
                }
            )
            return MultimodalFinding(
                modality=attachment.modality,
                source="audio_fallback",
                text="",
                summary="音频转写失败，已跳过多模态增强。",
                extracted_text=None,
                model_used=self.audio_model,
                file_name=attachment.file_name,
                error=error,
            )

    @staticmethod
    def _data_url(encoded: str, mime_type: str) -> str:
        return f"data:{mime_type};base64,{encoded}"
