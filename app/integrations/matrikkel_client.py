import httpx
import logging

logger = logging.getLogger(__name__)

GEONORGE_MATRIKKEL_URL = "https://ws.geonorge.no/matrikkel/v1/eiendom"

async def get_matrikkel_data(lat: float, lng: float) -> dict:
    """
    Query Geonorge Matrikkel REST API. Strict live mode with no fallbacks.
    """
    params = {
        "nord": round(lat, 6),
        "ost": round(lng, 6),
        "koordsys": 4326  # WGS84 system
    }
    
    headers = {
        "User-Agent": "CompassAI-SpatialApp/1.0",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            logger.info(f"Sending strict live request to Geonorge: ({lat}, {lng})")
            response = await client.get(GEONORGE_MATRIKKEL_URL, params=params, headers=headers)
            
            # This will raise HTTPStatusError immediately if status is 403, 404, 500 etc.
            response.raise_for_status()
            
            data = response.json()
            
            gnr = data.get("gardsnummer")
            bnr = data.get("bruksnummer")
            geometry = data.get("geometri", {})
            polygon_coordinates = geometry.get("coordinates", [[]])[0] if geometry else []
            
            if not gnr or not bnr:
                raise ValueError("Coordinates parsed successfully, but no GNR/BNR bound to this point.")

            logger.info(f"Live verification successful! GNR: {gnr}, BNR: {bnr}")
            return {
                "gnr": int(gnr),
                "bnr": int(bnr),
                "polygon": polygon_coordinates
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Live API execution failed with status {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"Geonorge rejected request with status code: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error inside matrikkel_client pipeline: {str(e)}")
            raise e