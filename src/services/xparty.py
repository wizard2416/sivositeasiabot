import os
import requests
import logging

logger = logging.getLogger(__name__)

def _sanitize(val):
    """Remove null bytes and control characters from strings."""
    if not isinstance(val, str):
        return val
    return val.replace('\x00', '').strip()

XPARTY_BASE_URL = "https://auto.trylab.online/xparty"
XPARTY_API_KEY = os.environ.get("XPARTY_API_KEY", "")
XENA_AVATAR_BASE_URL = os.environ.get("XENA_AVATAR_BASE_URL", "")  # Set this to the Xena avatar CDN base URL

def get_nickname_by_id(player_id: str) -> dict:
    """
    Get player nickname by ID.
    
    Returns:
        dict with keys:
            - success: bool
            - nickname: str (if success)
            - avatar: str (if success)
            - country: str (if success)
            - error: str (if failed)
    """
    if not XPARTY_API_KEY:
        return {"success": False, "error": "API key not configured"}
    
    try:
        response = requests.post(
            f"{XPARTY_BASE_URL}/info/get_nickname_by_id",
            json={
                "id": str(player_id),
                "api_key": XPARTY_API_KEY
            },
            timeout=30,
            verify=False
        )
        
        # Handle empty response
        if not response.text:
            return {"success": False, "error": "Empty response from API"}
        
        data = response.json()
        logger.info(f"Xparty API response for player {player_id}: {data}")
        
        if data.get("err") == False and data.get("user"):
            user = data["user"]
            # Handle nested structure: user.data contains the actual player info
            player_data = user.get("data", user)  # Fallback to user if no data key
            
            nickname = _sanitize(player_data.get("nickName", ""))
            country = _sanitize(player_data.get("country", ""))
            avatar = _sanitize(player_data.get("avatar", ""))
            uid = _sanitize(player_data.get("uid", player_id))
            
            logger.info(f"Parsed player data: nickname={nickname}, country={country}, avatar={avatar}")
            return {
                "success": True,
                "nickname": nickname,
                "avatar": avatar,
                "country": country,
                "uid": uid
            }
        else:
            error = data.get("err", "Unknown error")
            logger.warning(f"Xparty API error for player {player_id}: {error}")
            return {"success": False, "error": str(error)}
            
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timeout"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Xparty API request error: {e}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Xparty API error: {e}")
        return {"success": False, "error": str(e)}


def set_token(token: str) -> dict:
    """
    Set authentication token for Xparty.
    
    Returns:
        dict with keys:
            - success: bool
            - error: str (if failed)
    """
    if not XPARTY_API_KEY:
        return {"success": False, "error": "API key not configured"}
    
    try:
        response = requests.post(
            f"{XPARTY_BASE_URL}/control/set_token",
            json={
                "token": token,
                "api_key": XPARTY_API_KEY
            },
            timeout=30,
            verify=False
        )
        
        data = response.json()
        
        if data.get("state") == True:
            return {"success": True}
        else:
            return {"success": False, "error": data.get("err", "Token rejected")}
            
    except Exception as e:
        logger.error(f"Xparty set_token error: {e}")
        return {"success": False, "error": str(e)}


def recharge_by_id(player_id: str, amount: int, order_number: str, webhook_url: str) -> dict:
    """
    Send recharge request to Xparty API.
    Result will be sent to webhook.
    
    Returns:
        dict with keys:
            - success: bool (request accepted)
            - error: str (if failed to submit)
    """
    if not XPARTY_API_KEY:
        return {"success": False, "error": "API key not configured"}
    
    try:
        response = requests.post(
            f"{XPARTY_BASE_URL}/recharge/recharge_by_id",
            json={
                "id": str(player_id),
                "ammount": str(amount),
                "order_number": order_number,
                "webhook": webhook_url,
                "api_key": XPARTY_API_KEY
            },
            timeout=30,
            verify=False
        )
        
        if response.status_code == 200:
            return {"success": True}
        else:
            data = response.json() if response.text else {}
            return {"success": False, "error": data.get("err", f"HTTP {response.status_code}")}
            
    except Exception as e:
        logger.error(f"Xparty recharge error: {e}")
        return {"success": False, "error": str(e)}


def is_configured() -> bool:
    """Check if Xparty API is configured."""
    return bool(XPARTY_API_KEY)


def get_avatar_url(avatar_path: str) -> str:
    """Get full avatar URL from path."""
    if not avatar_path or not XENA_AVATAR_BASE_URL:
        return ""
    return f"{XENA_AVATAR_BASE_URL.rstrip('/')}/{avatar_path}"
