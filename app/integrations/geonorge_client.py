import httpx
import logging

# to know Municpality Number and change address to lat/lng

logger = logging.getLogger(__name__)

GEONORGE_KOMMUNE_URL = "https://ws.geonorge.no/kommuneinfo/v1/punkt"
GEONORGE_ADDRESS_URL = "https://ws.geonorge.no/adresser/v1/sok"

# to get Municpality
async def get_kommune_info(lat: float, lng: float) -> dict:
    """
    Fetch municipality info (kommunenummer) using WGS84 coordinates.
    """
    params = {
        "ost": lng,       # Longitude corresponds to Easting in EPSG:4326 context here
        "nord": lat,      # Latitude corresponds to Northing
        "koordsys": 4326  # WGS84 standard
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(GEONORGE_KOMMUNE_URL, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Geonorge Kommuneinfo API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Failed to fetch municipality info from Geonorge: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error in get_kommune_info: {str(e)}")
            raise RuntimeError("Connection to Geonorge Kommuneinfo failed")

async def get_coords_from_address(address: str) -> dict:
    """
    Resolve a free-text Norwegian address into lat/lng coordinates.
    """
    params = {
        "sok": address,
        "treffPerSide": 1
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(GEONORGE_ADDRESS_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            addresses = data.get("adresser", [])
            if not addresses:
                raise ValueError(f"No coordinates found for the address: {address}")
            
            # Extracting the first match
            target = addresses[0]
            return {
                "lat": target.get("representasjonspunkt", {}).get("lat"),
                "lng": target.get("representasjonspunkt", {}).get("lon"),
                "kommunenummer": target.get("kommunenummer"),
                "kommunenavn": target.get("kommunenavn")
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Geonorge Address API error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"Failed to resolve address from Geonorge: {e.response.status_code}")
        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in get_coords_from_address: {str(e)}")
            raise RuntimeError("Connection to Geonorge Address API failed")