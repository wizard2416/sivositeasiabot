import os
import re
import base64
import logging
from google import genai

logger = logging.getLogger(__name__)

class OCRService:
    def __init__(self):
        api_key = os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", "")
        base_url = os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL", "")
        
        if api_key and base_url:
            self.client = genai.Client(
                api_key=api_key,
                http_options={
                    'api_version': '',
                    'base_url': base_url
                }
            )
            logger.info("OCR service initialized with Gemini API (Replit AI Integrations)")
        else:
            self.client = None
            logger.warning("Gemini API not configured - OCR will not work")

    def extract_pin_from_image(self, image_bytes: bytes) -> dict:
        if not self.client:
            return {"success": False, "error": "OCR service not configured"}
        
        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": """You are an OCR expert. Extract the PIN number from this Asiacell recharge card image.

Rules:
- The PIN is a 13, 14, or 15 digit number
- It's usually found as a scratch-off code on the card
- Ignore any other numbers (serial numbers, barcodes, etc.)
- Return ONLY the digits, no spaces or dashes
- If you find multiple possible PINs, return the one that looks most like a recharge PIN
- If no valid PIN found, return exactly: NOT_FOUND"""},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                        ]
                    }
                ]
            )
            
            text = response.text.strip()
            logger.info(f"OCR response: {text[:50]}...")
            
            if "NOT_FOUND" in text.upper():
                return {"success": False, "error": "No valid PIN found in image"}
            
            digits = re.sub(r'\D', '', text)
            
            if 13 <= len(digits) <= 15:
                logger.info(f"OCR found PIN: {digits[:4]}****{digits[-4:]}")
                return {"success": True, "pin": digits}
            
            all_numbers = re.findall(r'\d{13,15}', text)
            if all_numbers:
                pin = all_numbers[0]
                logger.info(f"OCR extracted PIN: {pin[:4]}****{pin[-4:]}")
                return {"success": True, "pin": pin}
            
            return {"success": False, "error": "No valid 13-15 digit PIN found"}
            
        except Exception as e:
            logger.error(f"OCR error: {e}")
            return {"success": False, "error": str(e)}

    def extract_multiple_pins(self, image_bytes: bytes) -> dict:
        if not self.client:
            return {"success": False, "error": "OCR service not configured", "pins": []}
        
        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": """You are an OCR expert. Extract ALL PIN numbers from this image of Asiacell recharge cards.

Rules:
- Each PIN is a 13, 14, or 15 digit number
- Cards may show multiple PINs
- Return each PIN on a new line, ONLY the digits
- Ignore serial numbers, barcodes, and other numbers
- If no PINs found, return exactly: NOT_FOUND

Example output:
12345678901234
98765432109876"""},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                        ]
                    }
                ]
            )
            
            text = response.text.strip()
            logger.info(f"OCR multiple pins response: {text[:100]}...")
            
            if "NOT_FOUND" in text.upper():
                return {"success": False, "error": "No PINs found in image", "pins": []}
            
            all_numbers = re.findall(r'\d{13,15}', text)
            unique_pins = list(dict.fromkeys(all_numbers))
            
            if unique_pins:
                for pin in unique_pins:
                    logger.info(f"OCR found PIN: {pin[:4]}****{pin[-4:]}")
                return {"success": True, "pins": unique_pins}
            
            lines = text.split('\n')
            pins = []
            for line in lines:
                digits = re.sub(r'\D', '', line)
                if 13 <= len(digits) <= 15:
                    pins.append(digits)
            
            if pins:
                unique_pins = list(dict.fromkeys(pins))
                return {"success": True, "pins": unique_pins}
            
            return {"success": False, "error": "No valid PINs found", "pins": []}
            
        except Exception as e:
            logger.error(f"OCR multiple pins error: {e}")
            return {"success": False, "error": str(e), "pins": []}

    def extract_payment_info(self, image_bytes: bytes) -> dict:
        """Extract transaction number and amount from payment receipt images."""
        if not self.client:
            return {"success": False, "error": "OCR service not configured"}
        
        try:
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": """You are an OCR expert. Extract payment transaction information from this receipt image.

Look for:
1. Transaction number (رقم الحركة / رقم العملية) - a very long number (usually 20+ digits)
2. Amount (مبلغ التحويل / المبلغ) - the transferred amount in IQD

Return in this exact format:
TRANSACTION: <the long transaction number, digits only>
AMOUNT: <amount in numbers only, no commas>

If you can't find a value, use NOT_FOUND for that field.

Example output:
TRANSACTION: 20260114101214200101001665958037187721
AMOUNT: 18000"""},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
                        ]
                    }
                ]
            )
            
            text = response.text.strip()
            logger.info(f"OCR payment info response: {text[:100]}...")
            
            result = {"success": True, "transaction_number": None, "amount": None}
            
            # Extract transaction number
            trans_match = re.search(r'TRANSACTION:\s*(\d+)', text)
            if trans_match:
                result["transaction_number"] = trans_match.group(1)
                logger.info(f"OCR found transaction: {result['transaction_number'][:10]}...{result['transaction_number'][-10:]}")
            
            # Extract amount
            amount_match = re.search(r'AMOUNT:\s*(\d+)', text)
            if amount_match:
                result["amount"] = int(amount_match.group(1))
                logger.info(f"OCR found amount: {result['amount']}")
            
            if not result["transaction_number"] and not result["amount"]:
                return {"success": False, "error": "Could not extract payment info from image"}
            
            return result
            
        except Exception as e:
            logger.error(f"OCR payment info error: {e}")
            return {"success": False, "error": str(e)}
