import httpx
import logging

logger = logging.getLogger(__name__)

PLANSLURPEN_API_BASE = "https://www.planslurpen.no/api"


async def get_parcel_document(
    kommune_nr: str,
    plan_id: str,
    versjon: int | None = None,
    api_key: str | None = None
) -> dict:
    """
    Fetch the 'planbestemmelser' document for a selected plan/parcel.

    This is the original legal-text document (often a PDF) that the
    Planslurpen AI interpretation was generated from — the closest
    equivalent to a 'property/parcel document' for a given plan.

    Endpoint:
        GET /nedlasting/planbestemmelser/{kommunenummer}/{plan_id}
        Optional query param: versjon
    """
    print("from get_parcel_document")
    print(f"plan_id : {plan_id}")
    print(f"kommune_nr : {kommune_nr}")
    print(f"versjon : {versjon}")
    print(f"api_key : {api_key}")

    url = f"{PLANSLURPEN_API_BASE}/nedlasting/planbestemmelser/{kommune_nr}/{plan_id}"

    params = {}
    if versjon:
        params["versjon"] = versjon

    headers = {
        "User-Agent": "PropertyAgent/1.0",
        "Accept": "application/json"
    }
    try:
        async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:
            logger.info(f"Calling Planslurpen planbestemmelser: {url} params={params}")

            response = await client.get(url, params=params)

            if response.status_code != 200:
                return {
                    "adapter": "planbestemmelser_failed",
                    "status_code": response.status_code,
                    "error": response.text[:500]
                }

            content_type = response.headers.get("content-type", "")

            # Beta API — response shape isn't fully documented.
            # Handle both JSON-wrapped responses and raw file responses.
            if "application/json" in content_type:
                data = response.json()

                # Try common field names for a downloadable doc/url
                doc_url = (
                    data.get("dokumentUrl")
                    or data.get("documentUrl")
                    or data.get("url")
                    or data.get("filUrl")
                )

                return {
                    "adapter": "planbestemmelser",
                    "kommune": kommune_nr,
                    "plan_id": plan_id,
                    "document_url": doc_url,
                    "raw": data
                }

            else:
                # Raw file (PDF/text) returned directly
                return {
                    "adapter": "planbestemmelser",
                    "kommune": kommune_nr,
                    "plan_id": plan_id,
                    "content_type": content_type,
                    "content_length": len(response.content),
                    # NOTE: decide downstream whether to base64-encode,
                    # stream to storage, or pass through to Celery for PDF embedding
                    "raw_content": response.content
                }

    except Exception as e:
        logger.exception("Planbestemmelser fetch failed")
        return {
            "adapter": "planbestemmelser_failed",
            "error": str(e)
        }