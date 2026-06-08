import httpx
import logging

logger = logging.getLogger(__name__)

GEONORGE_KOMMUNE_URL = "https://ws.geonorge.no/kommuneinfo/v1/punkt"
GEONORGE_ADDRESS_URL = "https://ws.geonorge.no/adresser/v1/sok"

HEADERS = {
    "User-Agent": "PropertyAgent/1.0",
    "Accept": "application/json"
}


async def get_kommune_info(lat: float, lng: float) -> dict:
    """
    Get municipality information from coordinates.
    """

    params = {
        "nord": lat,
        "ost": lng,
        "koordsys": 4326
    }

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=15.0
    ) as client:

        try:
            response = await client.get(
                GEONORGE_KOMMUNE_URL,
                params=params
            )

            response.raise_for_status()

            data = response.json()

            return {
                "success": True,
                "kommunenummer": data.get("kommunenummer"),
                "kommunenavn": data.get("kommunenavn")
            }

        except Exception as e:
            logger.exception("Kommune lookup failed")

            return {
                "success": False,
                "error": str(e)
            }


async def get_coords_from_address(address: str) -> dict:
    """
    Resolve address -> coordinates + municipality info.
    """

    params = {
        "sok": address,
        "treffPerSide": 1,
        "asciiKompatibel": True
    }

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=15.0
    ) as client:

        try:
            response = await client.get(
                GEONORGE_ADDRESS_URL,
                params=params
            )

            response.raise_for_status()

            data = response.json()

            addresses = data.get("adresser", [])

            if not addresses:
                return {
                    "success": False,
                    "error": "Address not found"
                }

            item = addresses[0]

            point = item.get("representasjonspunkt", {})

            return {
                "success": True,

                "address": item.get("adressetekst"),

                "lat": point.get("lat")
                       or point.get("y"),

                "lng": point.get("lon")
                       or point.get("x"),

                "kommunenummer": item.get("kommunenummer"),
                "kommunenavn": item.get("kommunenavn"),

                "postnummer": item.get("postnummer"),
                "poststed": item.get("poststed")
            }

        except Exception as e:
            logger.exception("Address lookup failed")

            return {
                "success": False,
                "error": str(e)
            }