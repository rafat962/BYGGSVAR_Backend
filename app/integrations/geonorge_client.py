import httpx
import logging

logger = logging.getLogger(__name__)

GEONORGE_KOMMUNE_URL = "https://ws.geonorge.no/kommuneinfo/v1/punkt"
GEONORGE_ADDRESS_URL = "https://ws.geonorge.no/adresser/v1/sok"

async def get_kommune_info(lat: float, lng: float) -> dict:
    """
    Fetch live municipality info from Geonorge using WGS84 coordinates.
    """
    params = {
        "ost": lng,
        "nord": lat,
        "koordsys": 4326
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            logger.info(f"Fetching live Kommuneinfo for: {lat}, {lng}")
            response = await client.get(GEONORGE_KOMMUNE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            # The API returns the commune object directly
            return {
                "kommunenummer": data.get("kommunenummer"),
                "kommunenavn": data.get("kommunenavn")
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Geonorge Kommuneinfo API error: {e.response.status_code}")
            raise RuntimeError(f"Failed to fetch municipality info: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error in get_kommune_info: {str(e)}")
            raise RuntimeError("Connection to Geonorge Kommuneinfo failed")

async def get_coords_from_address(address: str) -> dict:
    """
    Resolve a free-text Norwegian address into real-time lat/lng coordinates.
    """
    params = {
        "sok": address,
        "treffPerSide": 1,
        "asciiKompatibel": True
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            logger.info(f"Resolving live address: {address}")
            response = await client.get(GEONORGE_ADDRESS_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            addresses = data.get("adresser", [])
            
            if not addresses:
                raise ValueError(f"No results found for address: {address}")
            
            # The structure is standard for Geonorge v1
            target = addresses[0]
            point = target.get("representasjonspunkt", {})
            
            return {
                "lat": point.get("lat"),
                "lng": point.get("lon"),
                "kommunenummer": target.get("kommunenummer"),
                "kommunenavn": target.get("kommunenavn")
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Geonorge Address API error: {e.response.status_code}")
            raise RuntimeError(f"Address resolution failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error in get_coords_from_address: {str(e)}")
            raise e