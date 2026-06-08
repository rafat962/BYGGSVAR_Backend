import httpx
import logging

logger = logging.getLogger(__name__)

NVE_FLOOD_URL = "https://gis3.nve.no/map/rest/services/Flom/MapServer/identify"
RIKSANTIKVAREN_HERITAGE_URL = "https://kart.ra.no/arcgis/rest/services/Kulturminner/MapServer/identify"

async def get_flood_risk(lat: float, lng: float) -> dict:
    """
    Query NVE Flood MapServer to check for environmental flood hazard zones.
    """
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "layers": "all",
        "tolerance": "5",  # Increased slightly to capture overlapping zones securely
        "mapExtent": f"{lng-0.005},{lat-0.005},{lng+0.005},{lat+0.005}",
        "imageDisplay": "800,600,96",
        "f": "json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            logger.info(f"Checking Live NVE Flood Risk for coordinates: ({lat}, {lng})")
            response = await client.get(NVE_FLOOD_URL, params=params)
            response.raise_for_status()
            
            result_data = response.json()
            results = result_data.get("results", [])
            
            if results:
                # Extract details from the first matching flood layer feature
                feature = results[0]
                attributes = feature.get("attributes", {})
                
                # NVE fields typically use 'flomsoneNavn' or 'gjentakelse' (return period)
                zone_name = attributes.get("flomsoneNavn") or attributes.get("gjentakelse") or "Active Hazard Zone"
                probability = attributes.get("sannsynlighet") or "1%"  # e.g., 100-year flood is 1%
                
                return {
                    "has_flood_risk": True,
                    "zone_type": str(zone_name),
                    "probability_per_year": str(probability)
                }
            
            return {
                "has_flood_risk": False,
                "zone_type": "None",
                "probability_per_year": "0%"
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"NVE Flood API error: {e.response.status_code}")
            raise RuntimeError(f"Failed to check flood risk from NVE: Status {e.response.status_code}")
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
        "tolerance": "5",
        "mapExtent": f"{lng-0.005},{lat-0.005},{lng+0.005},{lat+0.005}",
        "imageDisplay": "800,600,96",
        "f": "json"
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            logger.info(f"Checking Live Riksantikvaren Heritage Status for coordinates: ({lat}, {lng})")
            response = await client.get(RIKSANTIKVAREN_HERITAGE_URL, params=params)
            response.raise_for_status()
            
            result_data = response.json()
            results = result_data.get("results", [])
            print("results",results)
            # ضيف ده بعد الـ response.json() عشان تشوف في الـ Terminal السيرفر بيرد بإيه بالظبط
            logger.info(f"Raw NVE response: {result_data}")
            if results:
                feature = results[0]
                attributes = feature.get("attributes", {})
                
                # Extract heritage ID and category names based on Riksantikvaren schema
                heritage_id = attributes.get("kulturminneId") or attributes.get("lokalitetId")
                category = attributes.get("kulturminneKategori") or attributes.get("verneklasse") or "Protected Site"
                
                return {
                    "is_protected": True,
                    "heritage_id": str(heritage_id) if heritage_id else "Unknown",
                    "category": str(category)
                }
            
            return {
                "is_protected": False,
                "heritage_id": None,
                "category": "None"
            }
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Riksantikvaren API error: {e.response.status_code}")
            raise RuntimeError(f"Failed to check cultural heritage status: Status {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error in get_heritage_status: {str(e)}")
            raise RuntimeError("Connection to Riksantikvaren MapServer failed")