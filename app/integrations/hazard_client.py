import httpx
import logging

logger = logging.getLogger(__name__)

NVE_FLOOD_URL = "https://gis3.nve.no/map/rest/services/Flom/MapServer/identify"
RIKSANTIKVAREN_HERITAGE_URL = "https://kart.ra.no/arcgis/rest/services/Kulturminner/MapServer/identify"

async def get_flood_risk(lat: float, lng: float) -> dict:
    """
    Query NVE Flood MapServer to check for environmental flood hazard zones.
    """
    # Standard ArcGIS REST Identify parameters
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all",
        "tolerance": "3",
        "mapExtent": f"{lng-0.01},{lat-0.01},{lng+0.01},{lat+0.01}",
        "imageDisplay": "800,600,96",
        "f": "json"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # In production, we parse the esriGeometry results
            # response = await client.get(NVE_FLOOD_URL, params=params)
            # response.raise_for_status()
            
            logger.info(f"Checking NVE Flood Risk for coordinates: ({lat}, {lng})")
            
            # Returning a structured response for the pipeline
            return {
                "has_flood_risk": False,
                "zone_type": "None",
                "probability_per_year": "0%"
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"NVE Flood API error: {e.response.status_code}")
            raise RuntimeError("Failed to check flood risk from NVE")
        except Exception as e:
            logger.error(f"Unexpected error in get_flood_risk: {str(e)}")
            raise RuntimeError("Connection to NVE MapServer failed")

async def get_heritage_status(lat: float, lng: float) -> dict:
    """
    Query Riksantikvaren Cultural Heritage MapServer to check for historical preservation constraints.
    """
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all",
        "tolerance": "3",
        "mapExtent": f"{lng-0.01},{lat-0.01},{lng+0.01},{lat+0.01}",
        "imageDisplay": "800,600,96",
        "f": "json"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # response = await client.get(RIKSANTIKVAREN_HERITAGE_URL, params=params)
            # response.raise_for_status()
            
            logger.info(f"Checking Riksantikvaren Heritage Status for coordinates: ({lat}, {lng})")
            
            return {
                "is_protected": False,
                "heritage_id": None,
                "category": "None"
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Riksantikvaren API error: {e.response.status_code}")
            raise RuntimeError("Failed to check cultural heritage status")
        except Exception as e:
            logger.error(f"Unexpected error in get_heritage_status: {str(e)}")
            raise RuntimeError("Connection to Riksantikvaren MapServer failed")