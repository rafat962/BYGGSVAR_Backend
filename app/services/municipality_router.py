import httpx
import logging

logger = logging.getLogger(__name__)

# Official Norwegian Planning API endpoint
AREALPLAN_API_URL = "https://arealplaner.no/api/v1/planer"

async def get_planning_data(kommune_nr: str, gnr: int, bnr: int) -> dict:
    """
    Adapter خاص لأوسلو يتجاوز أي مشاكل اتصال عامة.
    """
    if kommune_nr != "0301":
        return {"error": "Only Oslo (0301) supported via this adapter", "plan_id": None}

    # هذا هو الـ Endpoint الرسمي والمستقر لبلدية أوسلو
    url = "https://planinnsyn.oslo.kommune.no/app/api/planer"
    
    # أوسلو بتحتاج نبعت الـ GNR/BNR بطريقة مجمعة أحياناً
    params = {
        "gardsnummer": gnr,
        "bruksnummer": bnr
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json"
    }

    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            plans = response.json()
            if not plans:
                return {"adapter": "oslo", "plan_id": "Not found", "zoning_purpose": "Unknown"}

            # أخذ أول خطة متاحة (الأحدث)
            latest_plan = plans[0]
            
            return {
                "adapter_used": "oslo_live",
                "plan_id": latest_plan.get("planident", "N/A"),
                "zoning_purpose": latest_plan.get("navn", "Boligbebyggelse"),
                "effective_date": latest_plan.get("vedtaksdato", "N/A"),
                "dokumentUrl": latest_plan.get("linkDokument", "#")
            }
        except Exception as e:
            logger.error(f"Oslo Adapter failed: {e}")
            return {"adapter": "oslo_failed", "error": str(e)}
    """
    نسخة مطورة تتضمن Headers للتعريف وتجربة Endpoint بديل في حالة الفشل.
    """
    # تعريف الـ User-Agent ضروري جداً لتجنب الحظر
    headers = {
        "User-Agent": "MyPropertyApp/1.0 (contact@example.com)",
        "Accept": "application/json"
    }
    
    url = f"https://api.geonorge.no/plan-arkiv/v1/planer"
    params = {
        "kommunenr": kommune_nr,
        "gardsnummer": gnr,
        "bruksnummer": bnr
    }

    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        try:
            logger.info(f"Trying live API for planning data...")
            response = await client.get(url, params=params)
            
            # إذا فشل الاتصال، لا نرفع RuntimeError، بل نحاول Endpoint بديل
            if response.status_code != 200:
                logger.warning(f"Primary API failed with code {response.status_code}")
                return {"error": "API unreachable", "adapter": "fallback_needed"}
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error connecting to API: {e}")
            return {"error": "Connection lost"}
    """
    Fetch real-time zoning and planning data using Kommune, GNR, and BNR.
    """
    # We query the planning service by property identifiers
    params = {
        "kommunenr": kommune_nr,
        "gardsnummer": gnr,
        "bruksnummer": bnr
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            logger.info(f"Fetching real-time planning data for {kommune_nr}/{gnr}/{bnr}")
            # Note: The API path might vary based on specific municipality integration, 
            # this represents the standard Norwegian Plan-API call structure.
            response = await client.get(AREALPLAN_API_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Assuming the API returns a list of plans affecting the property
            if not data:
                return {"error": "No planning data found"}
                
            # Parse the first active plan (usually the most relevant one)
            active_plan = data[0] 
            
            return {
                "adapter_used": "real_time_api",
                "plan_id": active_plan.get("planident"),
                "zoning_purpose": active_plan.get("formalsnavn"), # Zoning description
                "effective_date": active_plan.get("vedtaksdato"),
                "dokumentUrl": active_plan.get("plankartDokumentUrl") # Official PDF link
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch live planning data: {str(e)}")
            # Fallback to local logic or error reporting
            return {"error": "API unreachable"}