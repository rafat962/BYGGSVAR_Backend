import logging

logger = logging.getLogger(__name__)

def resolve_parcel_document_url(planning_data: dict) -> str | None:
    """
    Analyzes planning data from Planslurpen and extracts the most relevant 
    document URL (e.g., Plankart or primary PDF) for the property.
    
    Args:
        planning_data (dict): The output from the get_planning_data adapter.
        
    Returns:
        str | None: The resolved document URL or None if not found.
    """
    if not planning_data or planning_data.get("adapter") != "planslurpen":
        logger.warning("Invalid or failed planning data provided to resolver")
        return None

    plans = planning_data.get("plans", [])
    if not plans:
        logger.info("No plans found in planning data")
        return None

    # Flatten all documents from all plans to find the best match
    all_documents = []
    for plan in plans:
        all_documents.extend(plan.get("documents", []))

    if not all_documents:
        return None

    # Priority 1: Look for "Plankart" (Plan Map) which is usually the most important document
    for doc in all_documents:
        title = (doc.get("title") or "").lower()
        if "plankart" in title and doc.get("url"):
            logger.info(f"Resolved document URL via Plankart match: {doc['url']}")
            return doc["url"]

    # Priority 2: Look for any PDF document
    for doc in all_documents:
        if doc.get("type") == "pdf" and doc.get("url"):
            logger.info(f"Resolved document URL via PDF type match: {doc['url']}")
            return doc["url"]

    # Priority 3: Return the first available URL
    for doc in all_documents:
        if doc.get("url"):
            logger.info(f"Resolved document URL via first available link: {doc['url']}")
            return doc["url"]

    return None
