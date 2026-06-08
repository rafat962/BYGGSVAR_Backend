import logging

logger = logging.getLogger(__name__)

async def get_planning_data(kommune_nr: str, gnr: int, bnr: int) -> dict:
    """
    Route the planning request to the correct municipality adapter based on kommunenummer.
    """
    # Determine which adapter system to use based on the municipality number
    if kommune_nr == "0301":
        adapter = "oslo"
    elif kommune_nr in ["3803", "3804"]:
        adapter = "vestfoldkart"
    else:
        adapter = "kommunekart"  # Default fallback standard client

    logger.info(f"Routing planning request for Kommune: {kommune_nr} (GNR: {gnr}, BNR: {bnr}) using adapter: {adapter}")

    # In production, each adapter block will trigger specific API structures
    # Returning a unified internal schema for the orchestrator
    return {
        "adapter_used": adapter,
        "plan_id": "10503",
        "zoning_purpose": "Boligbebyggelse",  # Residential zoning
        "effective_date": "2020-11-09",
        "dokumentUrl": f"https://arkiv.kommune.no/plans/{kommune_nr}_{plan_id_mock(kommune_nr)}.pdf"
    }

def plan_id_mock(kommune_nr: str) -> str:
    # Quick helper for dynamic mock data generation
    return f"PLAN_{kommune_nr}_2026"