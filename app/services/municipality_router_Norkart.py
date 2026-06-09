

import httpx
import logging
import os
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Norkart API Base URLs
# The Arealplan API is part of Norkart's Plan- og geodata services.
AREALPLAN_API_URL = "https://arealplan.api.norkart.no"

def construct_matrikkel_id(kommune_nr: str, gnr: int, bnr: int, fnr: int = 0, snr: int = 0) -> str:
    """
    Constructs a 20-digit matrikkel-ID: KKKKGGGGGBBBBFFFFSSS
    This ID is used as a unique identifier for properties in Norkart's APIs.
    """
    try:
        return (
            f"{int(kommune_nr):04d}"
            f"{int(gnr):05d}"
            f"{int(bnr):04d}"
            f"{int(fnr):04d}"
            f"{int(snr):03d}"
        )
    except (ValueError, TypeError) as e:
        logger.error(f"Error constructing matrikkel_id: {e}")
        return ""

async def get_planning_data(
    kommune_nr: str,
    gnr: int,
    bnr: int,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches planning data from Norkart's Arealplan API for a specific property.
    Maps the result to the structure previously provided by the Planslurpen adapter.
    
    Args:
        kommune_nr: 4-digit municipality number
        gnr: Gårdsnummer
        bnr: Bruksnummer
        api_key: Norkart API key (optional, defaults to NORKART_API_KEY env var)
        
    Returns:
        A dictionary containing the count of plans and a list of mapped plan objects.
    """
    
    # Use provided API key or environment variable
    api_key = api_key or os.getenv("NORKART_API_KEY")
    
    if not api_key:
        logger.error("Norkart API key is missing")
        return {
            "adapter": "norkart_failed",
            "error": "Norkart API key is missing. Please set the NORKART_API_KEY environment variable."
        }

    matrikkel_id = construct_matrikkel_id(kommune_nr, gnr, bnr)
    if not matrikkel_id:
        return {
            "adapter": "norkart_failed",
            "error": "Invalid property identifiers provided."
        }
    
    # Norkart Arealplan API endpoint for property-based plan search.
    # We fetch plans associated with the specific matrikkel unit.
    url = f"{AREALPLAN_API_URL}/planer/eiendom/{matrikkel_id}"
    
    params = {
        "api_key": api_key
    }

    headers = {
        "User-Agent": "PropertyAgent/1.0",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
            logger.info(f"Calling Norkart Arealplan API: {url}")
            
            response = await client.get(url, params=params)

            if response.status_code != 200:
                logger.error(f"Norkart API returned status {response.status_code}: {response.text}")
                return {
                    "adapter": "norkart_failed",
                    "status_code": response.status_code,
                    "error": response.text[:500]
                }

            data = response.json()
            
            # Normalize the response to a list of plans
            raw_plans = data if isinstance(data, list) else data.get("planer", [])
            
            cleaned_plans = []

            for p in raw_plans:
                # Extract documents and map to client's format
                documents = []
                
                # Norkart's document list is usually in 'dokumenter'
                raw_docs = p.get("dokumenter") or []
                
                for d in raw_docs:
                    documents.append({
                        "title": d.get("tittel") or d.get("beskrivelse") or "Uten tittel",
                        "type": d.get("dokumenttype") or "dokument",
                        "url": d.get("url")
                    })

                # Fallback for plan map (common requirement)
                plankart_url = p.get("plankartUrl")
                if plankart_url:
                    documents.append({
                        "title": "Plankart",
                        "type": "pdf",
                        "url": plankart_url
                    })

                # Map Norkart fields to the client's expected Planslurpen structure
                # We prioritize national IDs and clear descriptors
                plan_id = p.get("planident")
                if isinstance(p.get("nasjonalArealplanId"), dict):
                    plan_id = p.get("nasjonalArealplanId").get("planidentifikasjon")

                cleaned_plans.append({
                    "plan_id": plan_id,
                    "kommune": p.get("kommunenummer") or kommune_nr,
                    "plan_name": p.get("plannavn") or "Navnløs plan",
                    "plan_status": (p.get("planstatus") or {}).get("beskrivelse") if isinstance(p.get("planstatus"), dict) else p.get("planstatus"),
                    "plan_type": (p.get("plantype") or {}).get("beskrivelse") if isinstance(p.get("plantype"), dict) else p.get("plantype"),
                    "documents": documents
                })

            return {
                "adapter": "norkart",
                "count": len(cleaned_plans),
                "plans": cleaned_plans
            }

    except Exception as e:
        logger.exception("Norkart API call failed")
        return {
            "adapter": "norkart_failed",
            "error": str(e)
        }
