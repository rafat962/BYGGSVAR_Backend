import httpx
import logging

logger = logging.getLogger(__name__)

PLANSLURPEN_API_URL = "https://www.planslurpen.no/api/planregister"


async def get_planning_data(
    kommune_nr: str,
    gnr: int,
    bnr: int
) -> dict:

    url = f"{PLANSLURPEN_API_URL}/{kommune_nr}/{gnr}/{bnr}"

    headers = {
        "User-Agent": "PropertyAgent/1.0",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(
            headers=headers,
            timeout=20.0
        ) as client:

            logger.info(f"Calling Planslurpen: {url}")

            response = await client.get(url)

            if response.status_code != 200:
                return {
                    "adapter": "planslurpen_failed",
                    "status_code": response.status_code,
                    "error": response.text[:500]
                }

            data = response.json()

            raw_plans = data.get("plan", [])

            cleaned_plans = []

            for p in raw_plans:

                # extract documents safely
                documents = []

                for d in p.get("documents", []) or []:
                    documents.append({
                        "title": d.get("title"),
                        "type": d.get("type"),
                        "url": d.get("url")
                    })

                # fallback PDF fields (common in Norwegian APIs)
                fallback_pdf = (
                    p.get("plankartUrl")
                    or p.get("plankartDokumentUrl")
                    or p.get("documentUrl")
                )

                if fallback_pdf:
                    documents.append({
                        "title": "Plankart / PDF",
                        "type": "pdf",
                        "url": fallback_pdf
                    })

                cleaned_plans.append({
                    "plan_id": (
                        p.get("nasjonalArealplanId", {})
                         .get("planidentifikasjon")
                    ),

                    "kommune": (
                        p.get("nasjonalArealplanId", {})
                         .get("administrativEnhet", {})
                         .get("kommunenummer")
                    ),

                    "plan_name": p.get("plannavn"),

                    "plan_status": (
                        p.get("planstatus", {})
                         .get("kodebeskrivelse")
                    ),

                    "plan_type": (
                        p.get("plantype", {})
                         .get("kodebeskrivelse")
                    ),

                    "documents": documents
                })

            return {
                "adapter": "planslurpen",
                "count": len(cleaned_plans),
                "plans": cleaned_plans
            }

    except Exception as e:
        logger.exception("Planslurpen failed")

        return {
            "adapter": "planslurpen_failed",
            "error": str(e)
        }