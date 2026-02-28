import os
import requests
import logging

logger = logging.getLogger(__name__)

SEVERBIL_API_KEY = os.environ.get('SEVERBIL_API_KEY', '')
SEVERBIL_BASE_URL = "https://siverbil.com/api"

class SeverbilAPI:
    def __init__(self):
        self.api_key = SEVERBIL_API_KEY
        self.base_url = SEVERBIL_BASE_URL
        
    def is_configured(self):
        return bool(self.api_key)
    
    def send_coins(self, player_id: str, coins: int) -> dict:
        """
        Send Xena Live coins to a player.
        
        Returns:
            dict with keys:
                - success: bool
                - order_id: str (if success)
                - error: str (if failed)
        """
        if not self.is_configured():
            logger.error("Severbil API key not configured")
            return {"success": False, "error": "API not configured"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "uid": player_id,
                "amount": coins
            }
            
            response = requests.post(
                f"{self.base_url}/send",
                json=payload,
                headers=headers,
                timeout=30
            )
            
            data = response.json()
            
            if response.status_code == 200 and data.get("success"):
                logger.info(f"Severbil: Successfully sent {coins} coins to player {player_id}")
                return {
                    "success": True,
                    "order_id": data.get("order_id", ""),
                    "message": data.get("message", "")
                }
            else:
                error_msg = data.get("error", data.get("message", "Unknown error"))
                logger.error(f"Severbil: Failed to send coins - {error_msg}")
                return {"success": False, "error": error_msg}
                
        except requests.Timeout:
            logger.error("Severbil: Request timeout")
            return {"success": False, "error": "Request timeout"}
        except requests.RequestException as e:
            logger.error(f"Severbil: Request error - {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"Severbil: Unexpected error - {e}")
            return {"success": False, "error": str(e)}
    
    def check_balance(self) -> dict:
        """Check Severbil account balance."""
        if not self.is_configured():
            return {"success": False, "error": "API not configured"}
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                f"{self.base_url}/balance",
                headers=headers,
                timeout=10
            )
            
            data = response.json()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "balance": data.get("balance", 0)
                }
            else:
                return {"success": False, "error": data.get("error", "Unknown error")}
                
        except Exception as e:
            logger.error(f"Severbil: Balance check error - {e}")
            return {"success": False, "error": str(e)}

severbil_api = SeverbilAPI()
