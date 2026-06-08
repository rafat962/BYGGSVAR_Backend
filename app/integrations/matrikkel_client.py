import httpx
import logging

logger = logging.getLogger(__name__)

# Completely open and public Geonorge Address Point-Search API
GEONORGE_ADDRESS_API = "https://ws.geonorge.no/adresser/v1/punktsok"

async def get_matrikkel_data(lat: float, lng: float) -> dict:
    """
    Query the open Geonorge Address API using exact expected parameter names (lat, lon).
    """
    # Updated to match the exact keys the API requires: lat and lon
    params = {
        "lat": round(lat, 6),
        "lon": round(lng, 6),
        "koordsys": 4326,  # WGS84 standard
        "radius": 50       # Search radius in meters
    }
    
    headers = {
        "User-Agent": "CompassAI-SpatialApp/1.0",
        "Accept": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            logger.info(f"Querying open Geonorge Address API at: ({lat}, {lng})")
            response = await client.get(GEONORGE_ADDRESS_API, params=params, headers=headers)
            
            response.raise_for_status()
            data = response.json()
            
            addresses = data.get("adresser", [])
            if not addresses:
                logger.warning(f"No address or property matches found within radius for: ({lat}, {lng})")
                raise ValueError(f"No registered property found at coordinates: ({lat}, {lng})")
            
            # Extract cadastre info from the closest resolved address record
            closest_match = addresses[0]
            gnr = closest_match.get("gardsnummer")
            bnr = closest_match.get("bruksnummer")
            
            # Extract point geometry to map spatial location
            repr_point = closest_match.get("representasjonspunkt", {})
            point_lat = repr_point.get("lat")
            point_lon = repr_point.get("lon")
            
            # Generate local bounding polygon from the resolved point coordinates
            polygon_coordinates = [
                [point_lon - 0.0005, point_lat - 0.0005],
                [point_lon + 0.0005, point_lat - 0.0005],
                [point_lon + 0.0005, point_lat + 0.0005],
                [point_lon - 0.0005, point_lat + 0.0005],
                [point_lon - 0.0005, point_lat - 0.0005]
            ]

            logger.info(f"Successfully resolved open data: GNR {gnr}, BNR {bnr}")
            return {
                "gnr": int(gnr) if gnr else None,
                "bnr": int(bnr) if bnr else None,
                "polygon": polygon_coordinates
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Open Geonorge API failure {e.response.status_code}: {e.response.text}")
            raise RuntimeError(f"Geonorge API error side: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error in open address pipeline execution: {str(e)}")
            raise e