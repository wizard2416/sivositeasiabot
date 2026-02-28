import os
import logging
import base64
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

AI_INTEGRATIONS_GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
AI_INTEGRATIONS_GEMINI_BASE_URL = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")

GENERATED_IMAGES_DIR = Path("data/generated_images")
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

client = None
if AI_INTEGRATIONS_GEMINI_BASE_URL and AI_INTEGRATIONS_GEMINI_API_KEY:
    client = genai.Client(
        api_key=AI_INTEGRATIONS_GEMINI_API_KEY,
        http_options={
            'api_version': '',
            'base_url': AI_INTEGRATIONS_GEMINI_BASE_URL   
        }
    )
    logger.info("AI Image generation service initialized with Gemini")
else:
    logger.warning("Gemini AI integration not configured for image generation")


def generate_image(prompt: str) -> tuple[bool, str, str | None]:
    """
    Generate an image from a text prompt using Gemini.
    Returns: (success: bool, message: str, file_path: str | None)
    """
    if not client:
        return False, "خدمة توليد الصور غير متاحة", None
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )
        
        if not response.candidates:
            return False, "لم يتم توليد صورة - لا توجد نتائج", None
        
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return False, "لم يتم توليد صورة - محتوى فارغ", None
        
        for part in candidate.content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                mime_type = part.inline_data.mime_type or "image/png"
                image_data = part.inline_data.data
                
                if isinstance(image_data, str):
                    image_bytes = base64.b64decode(image_data)
                else:
                    image_bytes = image_data
                
                ext = "png" if "png" in mime_type else "jpg"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"ai_image_{timestamp}.{ext}"
                file_path = GENERATED_IMAGES_DIR / filename
                
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                
                logger.info(f"Generated image saved to {file_path}")
                return True, "تم توليد الصورة بنجاح!", str(file_path)
        
        return False, "لم يتم العثور على بيانات الصورة في الرد", None
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Image generation error: {error_msg}")
        
        if "FREE_CLOUD_BUDGET_EXCEEDED" in error_msg:
            return False, "تم تجاوز حد الميزانية السحابية المجانية", None
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            return False, "تم حظر الطلب بسبب قيود الأمان", None
        else:
            return False, f"خطأ في توليد الصورة: {error_msg[:100]}", None


def is_available() -> bool:
    """Check if the AI image generation service is available."""
    return client is not None
