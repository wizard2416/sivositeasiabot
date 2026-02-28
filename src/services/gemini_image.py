import os
import base64
import tempfile
import logging
import uuid
from typing import List, Tuple, Optional
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GENERATED_IMAGES_DIR = "data/generated_images"
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

AI_INTEGRATIONS_GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY")
AI_INTEGRATIONS_GEMINI_BASE_URL = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL")

client = None
if AI_INTEGRATIONS_GEMINI_API_KEY and AI_INTEGRATIONS_GEMINI_BASE_URL:
    client = genai.Client(
        api_key=AI_INTEGRATIONS_GEMINI_API_KEY,
        http_options={
            'api_version': '',
            'base_url': AI_INTEGRATIONS_GEMINI_BASE_URL
        }
    )

async def analyze_prompt_completeness(prompt: str) -> Tuple[bool, Optional[str]]:
    """Check if prompt is complete enough for image generation. Returns (is_complete, question_to_ask)"""
    if not client:
        raise Exception("Gemini API not configured")
    
    try:
        analysis_prompt = f"""Analyze this image generation prompt and determine if it's complete enough to create a good image.
        
Prompt: "{prompt}"

If the prompt is vague, unclear, or missing important details, respond with a helpful question in Arabic to clarify. 
If the prompt is clear and complete enough, respond with just "OK".

Important details to check:
- Style (realistic, cartoon, artistic, etc.)
- Colors or color scheme
- Size/dimensions/aspect
- Specific elements or objects
- Mood or atmosphere
- Background

Keep questions short and in Arabic. Ask only ONE question at a time about the most important missing detail."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=analysis_prompt
        )
        
        if response and response.text:
            result = response.text.strip()
            if result == "OK" or result.lower() == "ok":
                return (True, None)
            return (False, result)
        return (True, None)
    except Exception as e:
        logger.error(f"Prompt analysis error: {e}")
        return (True, None)

async def transcribe_arabic_voice(audio_path: str) -> str:
    if not client:
        raise Exception("Gemini API not configured")
    
    try:
        with open(audio_path, 'rb') as f:
            audio_bytes = f.read()
        
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": "Transcribe this Arabic voice message. Return only the transcribed text in Arabic. If the audio is in another language, still transcribe it."},
                        {"inline_data": {"mime_type": "audio/ogg", "data": audio_b64}}
                    ]
                }
            ]
        )
        
        if response and response.text:
            return response.text.strip()
        return ""
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        raise

async def generate_image_from_prompt(prompt: str) -> str:
    if not client:
        raise Exception("Gemini API not configured")
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )
        
        if not response.candidates:
            raise ValueError("No candidates in response")
        
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            raise ValueError("No content parts in response")
        
        for part in candidate.content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                mime_type = part.inline_data.mime_type or "image/png"
                image_data = part.inline_data.data
                
                if isinstance(image_data, bytes):
                    image_bytes = image_data
                else:
                    image_bytes = base64.b64decode(image_data)
                
                ext = "png" if "png" in mime_type else "jpg"
                filename = f"{uuid.uuid4().hex}.{ext}"
                filepath = os.path.join(GENERATED_IMAGES_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(image_bytes)
                return filepath
        
        raise ValueError("No image data in response")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        raise

async def edit_image_with_prompt(image_path: str, edit_prompt: str) -> str:
    """Edit an existing image based on a prompt"""
    if not client:
        raise Exception("Gemini API not configured")
    
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        ext = image_path.lower().split('.')[-1]
        mime_type = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp'] else "image/jpeg"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[
                {
                    "role": "user", 
                    "parts": [
                        {"text": f"Edit this image: {edit_prompt}"},
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}}
                    ]
                }
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            )
        )
        
        if not response.candidates:
            raise ValueError("No candidates in response")
        
        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            raise ValueError("No content parts in response")
        
        for part in candidate.content.parts:
            if hasattr(part, 'inline_data') and part.inline_data:
                out_mime = part.inline_data.mime_type or "image/png"
                image_data = part.inline_data.data
                
                if isinstance(image_data, bytes):
                    result_bytes = image_data
                else:
                    result_bytes = base64.b64decode(image_data)
                
                out_ext = "png" if "png" in out_mime else "jpg"
                filename = f"{uuid.uuid4().hex}.{out_ext}"
                filepath = os.path.join(GENERATED_IMAGES_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(result_bytes)
                return filepath
        
        raise ValueError("No image data in response")
    except Exception as e:
        logger.error(f"Image edit error: {e}")
        raise

async def edit_multiple_images(image_paths: List[str], edit_prompt: str) -> List[str]:
    """Edit multiple images with the same prompt"""
    results = []
    for path in image_paths:
        try:
            result = await edit_image_with_prompt(path, edit_prompt)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to edit {path}: {e}")
    return results

async def describe_image(image_path: str) -> str:
    """Describe what's in an image"""
    if not client:
        raise Exception("Gemini API not configured")
    
    try:
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        ext = image_path.lower().split('.')[-1]
        mime_type = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp'] else "image/jpeg"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": "Describe this image in Arabic. What do you see? Be concise."},
                        {"inline_data": {"mime_type": mime_type, "data": image_b64}}
                    ]
                }
            ]
        )
        
        if response and response.text:
            return response.text.strip()
        return ""
    except Exception as e:
        logger.error(f"Image description error: {e}")
        raise
