import asyncio
import logging
from app.integrations.geonorge_client import get_kommune_info, get_coords_from_address
from app.integrations.matrikkel_client import get_matrikkel_data
from app.integrations.hazard_client import get_flood_risk, get_heritage_status
from app.services.municipality_router import get_planning_data

logger = logging.getLogger(__name__)

async def process_coordinates(lat: float, lng: float) -> dict:
    """
    Scenario A: Coordinate-based orchestration pipeline.
    Executes multiple independent API calls in parallel using asyncio.gather.
    """
    logger.info(f"Starting GIS orchestration for coordinates: ({lat}, {lng})")

    # STEP 1 & 2: Fetch Kommune info and Matrikkel data concurrently
    kommune_task = get_kommune_info(lat, lng)
    matrikkel_task = get_matrikkel_data(lat, lng)

    kommune_data, matrikkel_data = await asyncio.gather(kommune_task, matrikkel_task)

    kommune_nr = kommune_data.get("kommunenummer")
    gnr = matrikkel_data.get("gnr")
    bnr = matrikkel_data.get("bnr")
    polygon = matrikkel_data.get("polygon")

    if not kommune_nr or not gnr or not bnr:
        raise ValueError("Failed to resolve baseline property indicators (Kommune, GNR, or BNR)")

    # STEP 3, 4, 5A, & 5B: Trigger subsequent parallel queries using resolved identifiers
    planning_task = get_planning_data(kommune_nr, gnr, bnr)
    flood_task = get_flood_risk(lat, lng)
    heritage_task = get_heritage_status(lat, lng)

    planning_data, flood_data, heritage_data = await asyncio.gather(
        planning_task, flood_task, heritage_task
    )
    print("Planning Data",planning_data)

    # STEP 6: PDF Registry and Celery Queue placeholder
    # Injected later: trigger_pdf_pipeline(planning_data.get("dokumentUrl"), ... )

    # Assembling the final clean response structure
    return {
        "status": "success",
        "search_method": "coordinates",
        "kommunenummer": kommune_nr,
        "property_id": {
            "gnr": gnr,
            "bnr": bnr,
            "key": f"prop_{kommune_nr}_{gnr}_{bnr}"
        },
        "boundary_polygon": polygon,
        "planning_details": planning_data,
        "environmental_hazards": {
            "flood": flood_data,
            "heritage": heritage_data
        }
    }

async def process_address(address: str) -> dict:
    """
    Scenario B: Address-based orchestration pipeline.
    Resolves the text address to coordinates first, then passes control to Scenario A.
    """
    logger.info(f"Starting Address orchestration for: '{address}'")

    # STEP 0: Resolve free-text address to physical coordinates
    resolved_coords = await get_coords_from_address(address)
    lat = resolved_coords.get("lat")
    lng = resolved_coords.get("lng")

    if not lat or not lng:
        raise ValueError(f"Could not extract spatial coordinates for address: {address}")

    # Seamlessly hand over execution to Scenario A (DRY Principle)
    result = await process_coordinates(lat, lng)
    
    # Enrich result metadata to indicate it started as an address search
    result["search_method"] = "address"
    result["input_address"] = address
    return result