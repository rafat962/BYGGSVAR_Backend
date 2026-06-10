"""
app/services/municipality_router.py

BYGGSVAR Platform — Municipality Router & Adapter Layer
=========================================================
Routes Norwegian planning data requests (arealplaner / kommuneplaner) to the
correct adapter based on kommunenummer, then normalises the raw responses into
a single unified BYGGSVAR schema.

Adapter hierarchy (tried in order):
  1. KommunekartAdapter   — primary source (arealplaner.no / Norkart backend)
  2. GeoInnsynAdapter     — stub (future)
  3. VestfoldkartAdapter  — stub (future)
  4. PlanslurpenAdapter   — fallback / supplementary

All HTTP traffic mimics a regular browser session by spoofing User-Agent and
Referer headers so the public portals treat our backend as a citizen browsing
the map.  No commercial API keys are required.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & shared browser-spoof headers
# ---------------------------------------------------------------------------

# Realistic browser UA used across all adapters
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# arealplaner.no / Norkart internal API base
AREALPLANER_API_BASE = "https://api.arealplaner.no/api/kunder"
AREALPLANER_PORTAL_BASE = "https://arealplaner.no"

# Planslurpen public API
PLANSLURPEN_API_URL = "https://www.planslurpen.no/api/planregister"

# Matrikkel WFS (Kartverket) — used for coordinate → gnr/bnr lookups
MATRIKKEL_WFS_URL = (
    "https://wfs.geonorge.no/skwms1/wfs.matrikkel"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeName=matrikkel:MatrikkelenhetTeig"
    "&outputFormat=application/json"
)

# ---------------------------------------------------------------------------
# Kommunenummer → arealplaner.no customer slug mapping
#
# The arealplaner.no API uses URL slugs of the form   <name><kommunenummer>
# e.g. "malvik5047" for Malvik (5047), "oslo0301" for Oslo (0301).
# This mapping covers the most common municipalities; extend as needed.
# ---------------------------------------------------------------------------
KOMMUNEKART_SLUG_MAP: dict[str, str] = {
    "0301": "oslo0301",
    "1103": "stavanger1103",
    "1201": "bergen4601",     # merged into 4601 in 2024, keep both keys
    "4601": "bergen4601",
    "5001": "trondheim5001",
    "1804": "bodo1804",
    "3201": "kongsberg3201",
    "3212": "nesodden3212",
    "3214": "frogn3214",
    "4204": "kristiansand4204",
    "4602": "kinn4602",
    "5030": "orkland5030",
    "5047": "malvik5047",
    "5053": "inderoy5053",
    "5054": "indre-fosen5054",
    "1114": "bjerkreim1114",
    "5530": "senja5530",
}

# Which kommunenummer values are served by arealplaner.no/Kommunekart
# (anything in the slug map is considered "Kommunekart territory")
KOMMUNEKART_MUNICIPALITIES: set[str] = set(KOMMUNEKART_SLUG_MAP.keys())


# ---------------------------------------------------------------------------
# Unified output schema
# ---------------------------------------------------------------------------

@dataclass
class PlanDocument:
    """A single document (PDF, SOSI, etc.) attached to a plan."""
    title: str | None
    doc_type: str | None       # "pdf", "sosi", "image", etc.
    url: str | None


@dataclass
class NormalisedPlan:
    """Unified BYGGSVAR plan record returned by every adapter."""
    municipality_id: str
    plan_id: str | None
    plan_name: str | None
    plan_type: str | None
    plan_status: str | None
    document_links: list[PlanDocument] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "municipality_id": self.municipality_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "plan_type": self.plan_type,
            "plan_status": self.plan_status,
            "document_links": [
                {
                    "title": d.title,
                    "doc_type": d.doc_type,
                    "url": d.url,
                }
                for d in self.document_links
            ],
        }


@dataclass
class RouterResult:
    """Top-level result returned by the router."""
    adapter: str
    municipality_id: str
    gnr: int | None
    bnr: int | None
    plans: list[NormalisedPlan] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "municipality_id": self.municipality_id,
            "gnr": self.gnr,
            "bnr": self.bnr,
            "plan_count": len(self.plans),
            "plans": [p.to_dict() for p in self.plans],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Abstract adapter base
# ---------------------------------------------------------------------------

class BaseAdapter(ABC):
    """
    Every adapter must implement `fetch_plans`.
    Adapters should raise exceptions freely; the router catches them and
    falls through to the next adapter.
    """

    name: str = "base"

    # Shared httpx client settings used by all adapters
    DEFAULT_TIMEOUT = 25.0
    DEFAULT_HEADERS: dict[str, str] = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.7",
    }

    @abstractmethod
    async def fetch_plans(
        self,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
        x: float | None,
        y: float | None,
    ) -> list[NormalisedPlan]:
        """
        Fetch and return normalised plans.

        Parameters
        ----------
        municipality_id : str
            4-digit Norwegian kommunenummer, e.g. "5047".
        gnr : int | None
            Gårdsnummer (parcel number).
        bnr : int | None
            Bruksnummer (property number).
        x : float | None
            ETRS89 / UTM33N easting (EPSG:25833) — optional coordinate lookup.
        y : float | None
            ETRS89 / UTM33N northing.
        """

    # ------------------------------------------------------------------
    # Shared helper: log outbound request details for debugging / testing
    # ------------------------------------------------------------------
    @staticmethod
    def _log_request(method: str, url: str, headers: dict, params: dict | None = None) -> None:
        logger.debug(
            "[HTTP REQUEST] %s %s | headers=%s | params=%s",
            method.upper(), url, json.dumps(headers, ensure_ascii=False), params
        )
        # Also print to stdout when running in __main__ test mode
        print(
            f"\n{'='*60}\n"
            f"  HTTP {method.upper()}  {url}\n"
            f"  HEADERS: {json.dumps(headers, indent=4, ensure_ascii=False)}\n"
            f"  PARAMS:  {params}\n"
            f"{'='*60}"
        )


# ---------------------------------------------------------------------------
# Adapter 1 — KommunekartAdapter (arealplaner.no / Norkart internal API)
# ---------------------------------------------------------------------------

class KommunekartAdapter(BaseAdapter):
    """
    Reverse-engineered adapter for arealplaner.no (Norkart Plandialog).

    The public arealplaner.no portal makes XHR calls to:
      https://api.arealplaner.no/api/kunder/<slug>/arealplaner
          ?kommunenummer=<knr>&gnr=<gnr>&bnr=<bnr>

    This returns a list of plan objects.  For each plan, documents are fetched
    from the same API's /arealplaner/<planId>/dokumenter endpoint.

    The portal sets Referer: https://arealplaner.no/<slug>/arealplaner/...
    and Origin: https://arealplaner.no — we replicate both.
    """

    name = "kommunekart"

    # ------------------------------------------------------------------
    # Step 1: resolve slug from kommunenummer
    # ------------------------------------------------------------------
    def _get_slug(self, municipality_id: str) -> str:
        slug = KOMMUNEKART_SLUG_MAP.get(municipality_id)
        if slug is None:
            raise ValueError(
                f"No arealplaner.no slug found for kommunenummer '{municipality_id}'. "
                "Add it to KOMMUNEKART_SLUG_MAP or use a different adapter."
            )
        return slug

    # ------------------------------------------------------------------
    # Step 2: search plans by gnr / bnr
    # ------------------------------------------------------------------
    async def _search_plans(
        self,
        client: httpx.AsyncClient,
        slug: str,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
    ) -> list[dict]:
        """
        Call the arealplaner.no internal search endpoint and return raw plan dicts.
        """
        url = f"{AREALPLANER_API_BASE}/{slug}/arealplaner"
        params: dict[str, Any] = {"kommunenummer": municipality_id}
        if gnr is not None:
            params["gnr"] = gnr
        if bnr is not None:
            params["bnr"] = bnr

        # Spoof browser session: set Referer to the municipality's portal page
        headers = {
            **self.DEFAULT_HEADERS,
            "Referer": f"{AREALPLANER_PORTAL_BASE}/{slug}/arealplaner",
            "Origin": AREALPLANER_PORTAL_BASE,
        }

        self._log_request("GET", url, headers, params)

        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        # The API may return either a list directly or {"arealplaner": [...]}
        if isinstance(data, list):
            return data
        return data.get("arealplaner") or data.get("plans") or []

    # ------------------------------------------------------------------
    # Step 3: fetch documents for a single plan
    # ------------------------------------------------------------------
    async def _fetch_documents(
        self,
        client: httpx.AsyncClient,
        slug: str,
        plan_id: int | str,
    ) -> list[dict]:
        """
        Fetch document list for a single plan from the arealplaner.no API.
        Returns a (possibly empty) list of raw document dicts.
        """
        url = f"{AREALPLANER_API_BASE}/{slug}/arealplaner/{plan_id}/dokumenter"
        headers = {
            **self.DEFAULT_HEADERS,
            "Referer": (
                f"{AREALPLANER_PORTAL_BASE}/{slug}/arealplaner/{plan_id}"
            ),
            "Origin": AREALPLANER_PORTAL_BASE,
        }

        self._log_request("GET", url, headers)

        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            logger.warning("No documents endpoint for plan %s/%s", slug, plan_id)
            return []
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return data
        return data.get("dokumenter") or data.get("documents") or []

    # ------------------------------------------------------------------
    # Step 4: normalise a raw plan dict + its documents
    # ------------------------------------------------------------------
    def _normalise_plan(
        self,
        raw: dict,
        municipality_id: str,
        docs_raw: list[dict],
    ) -> NormalisedPlan:
        """
        Map arealplaner.no JSON fields → NormalisedPlan.

        The Norkart API uses nested nasjonal arealplan-id objects.  We
        handle both flat and nested shapes.
        """
        nasjonal = raw.get("nasjonalArealplanId") or {}
        plan_id = (
            raw.get("planidentifikasjon")
            or nasjonal.get("planidentifikasjon")
            or str(raw.get("id", ""))
            or None
        )
        plan_name = raw.get("plannavn") or raw.get("name")
        plan_type = (
            (raw.get("plantype") or {}).get("kodebeskrivelse")
            or raw.get("plantype")
        )
        plan_status = (
            (raw.get("planstatus") or {}).get("kodebeskrivelse")
            or raw.get("planstatus")
        )

        documents: list[PlanDocument] = []

        for doc in docs_raw:
            raw_url = doc.get("url") or doc.get("nedlastingslenke") or doc.get("downloadUrl")
            if not raw_url:
                # Build download URL from the known pattern if we have a doc id
                doc_id = doc.get("id")
                if doc_id and plan_id:
                    raw_url = (
                        f"{AREALPLANER_API_BASE}/{municipality_id}/"
                        f"dokumenter/{doc_id}/download"
                    )
            documents.append(
                PlanDocument(
                    title=doc.get("tittel") or doc.get("title") or doc.get("filename"),
                    doc_type=self._infer_doc_type(
                        doc.get("dokumenttype") or doc.get("type") or "",
                        raw_url or "",
                    ),
                    url=raw_url,
                )
            )

        # Fallback: top-level PDF links sometimes embedded in the plan itself
        for key in ("plankartUrl", "plankartDokumentUrl", "documentUrl", "dokumentUrl"):
            fallback = raw.get(key)
            if fallback:
                documents.append(
                    PlanDocument(title="Plankart / PDF", doc_type="pdf", url=fallback)
                )

        return NormalisedPlan(
            municipality_id=municipality_id,
            plan_id=plan_id,
            plan_name=plan_name,
            plan_type=plan_type,
            plan_status=plan_status,
            document_links=documents,
        )

    @staticmethod
    def _infer_doc_type(type_hint: str, url: str) -> str:
        hint = (type_hint + url).lower()
        if ".pdf" in hint or "pdf" in hint:
            return "pdf"
        if ".sosi" in hint or "sosi" in hint:
            return "sosi"
        if ".shp" in hint or "shapefile" in hint:
            return "shapefile"
        if ".gml" in hint:
            return "gml"
        if any(ext in hint for ext in [".jpg", ".jpeg", ".png", ".tif"]):
            return "image"
        return "unknown"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    async def fetch_plans(
        self,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
        x: float | None,
        y: float | None,
    ) -> list[NormalisedPlan]:
        slug = self._get_slug(municipality_id)
        logger.info(
            "[KommunekartAdapter] municipality=%s slug=%s gnr=%s bnr=%s",
            municipality_id, slug, gnr, bnr,
        )

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT, follow_redirects=True) as client:
            raw_plans = await self._search_plans(client, slug, municipality_id, gnr, bnr)
            if not raw_plans:
                logger.warning(
                    "[KommunekartAdapter] No plans returned for municipality=%s gnr=%s bnr=%s",
                    municipality_id, gnr, bnr,
                )
                return []

            normalised: list[NormalisedPlan] = []
            for raw in raw_plans:
                # The internal DB id (integer) is used for document lookups
                db_id = raw.get("id")
                if db_id is not None:
                    try:
                        docs_raw = await self._fetch_documents(client, slug, db_id)
                    except Exception as exc:
                        logger.warning(
                            "[KommunekartAdapter] Document fetch failed for plan %s: %s",
                            db_id, exc,
                        )
                        docs_raw = []
                else:
                    docs_raw = []

                normalised.append(
                    self._normalise_plan(raw, municipality_id, docs_raw)
                )

            return normalised


# ---------------------------------------------------------------------------
# Adapter 2 — GeoInnsynAdapter  (stub — future implementation)
# ---------------------------------------------------------------------------

class GeoInnsynAdapter(BaseAdapter):
    """
    Placeholder for GeoInnsyn (Norconsult / Geodata AS) municipalities.

    GeoInnsyn portal: https://kommunekart.com / https://geoinnsyn.no
    Known XHR pattern (to be reverse-engineered):
      GET https://www.kommunekart.cohttps://api.arealplaner.no/api/kunder/malvik5047/arealplanerm/map/{slug}/plan?knr=...&gnr=...&bnr=...
    """

    name = "geoinnsyn"

    async def fetch_plans(
        self,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
        x: float | None,
        y: float | None,
    ) -> list[NormalisedPlan]:
        # TODO: implement when GeoInnsyn XHR endpoints are confirmed
        raise NotImplementedError(
            "GeoInnsynAdapter is not yet implemented. "
            "Trace network traffic on kommunekart.com or geoinnsyn.no for this municipality "
            "to identify the correct internal JSON endpoints."
        )


# ---------------------------------------------------------------------------
# Adapter 3 — VestfoldkartAdapter  (stub — future implementation)
# ---------------------------------------------------------------------------

class VestfoldkartAdapter(BaseAdapter):
    """
    Placeholder for Vestfoldkart municipalities (Vestfold og Telemark).

    Portal: https://www.vestfoldkart.no
    The portal appears to use an Esri-based backend; ArcGIS REST endpoints
    need to be reverse-engineered per municipality.
    """

    name = "vestfoldkart"

    async def fetch_plans(
        self,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
        x: float | None,
        y: float | None,
    ) -> list[NormalisedPlan]:
        # TODO: implement when Vestfoldkart REST endpoints are confirmed
        raise NotImplementedError(
            "VestfoldkartAdapter is not yet implemented. "
            "Trace network traffic on vestfoldkart.no to find the ArcGIS REST endpoints."
        )


# ---------------------------------------------------------------------------
# Adapter 4 — PlanslurpenAdapter  (fallback / supplementary)
# ---------------------------------------------------------------------------

class PlanslurpenAdapter(BaseAdapter):
    """
    Fallback adapter using the Planslurpen aggregation API.

    Planslurpen.no aggregates plan data from multiple Norwegian municipalities
    and exposes a clean REST endpoint:
      GET https://www.planslurpen.no/api/planregister/{knr}/{gnr}/{bnr}

    Used only when the primary adapter fails or the municipality is not in
    the Kommunekart slug map.
    """

    name = "planslurpen"

    async def fetch_plans(
        self,
        municipality_id: str,
        gnr: int | None,
        bnr: int | None,
        x: float | None,
        y: float | None,
    ) -> list[NormalisedPlan]:
        if gnr is None or bnr is None:
            raise ValueError(
                "PlanslurpenAdapter requires both gnr and bnr to be provided."
            )

        url = f"{PLANSLURPEN_API_URL}/{municipality_id}/{gnr}/{bnr}"
        headers = {
            **self.DEFAULT_HEADERS,
            "Referer": "https://www.planslurpen.no/",
        }

        self._log_request("GET", url, headers)

        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

        raw_plans: list[dict] = data.get("plan") or data.get("plans") or []
        return [self._normalise(p, municipality_id) for p in raw_plans]

    @staticmethod
    def _normalise(raw: dict, municipality_id: str) -> NormalisedPlan:
        nasjonal = raw.get("nasjonalArealplanId") or {}
        plan_id = (
            nasjonal.get("planidentifikasjon")
            or raw.get("planidentifikasjon")
            or raw.get("id")
        )

        documents: list[PlanDocument] = []
        for doc in raw.get("documents") or []:
            documents.append(
                PlanDocument(
                    title=doc.get("title"),
                    doc_type=doc.get("type"),
                    url=doc.get("url"),
                )
            )
        for key in ("plankartUrl", "plankartDokumentUrl", "documentUrl"):
            if raw.get(key):
                documents.append(
                    PlanDocument(title="Plankart / PDF", doc_type="pdf", url=raw[key])
                )

        return NormalisedPlan(
            municipality_id=municipality_id,
            plan_id=plan_id,
            plan_name=raw.get("plannavn") or raw.get("name"),
            plan_type=(raw.get("plantype") or {}).get("kodebeskrivelse") or raw.get("plantype"),
            plan_status=(raw.get("planstatus") or {}).get("kodebeskrivelse") or raw.get("planstatus"),
            document_links=documents,
        )


# ---------------------------------------------------------------------------
# Municipality Router
# ---------------------------------------------------------------------------

class MunicipalityRouter:
    """
    Central routing engine for the BYGGSVAR platform.

    Decision tree
    -------------
    1. If municipality_id is in KOMMUNEKART_MUNICIPALITIES → try KommunekartAdapter
    2. On failure, try PlanslurpenAdapter as fallback
    3. Stub adapters (GeoInnsyn, Vestfoldkart) are wired in but raise
       NotImplementedError until their endpoints are confirmed.

    All adapters return List[NormalisedPlan]; the router wraps them in
    a RouterResult and records which adapter ultimately succeeded.
    """

    def __init__(self) -> None:
        self._kommunekart = KommunekartAdapter()
        self._planslurpen = PlanslurpenAdapter()
        self._geoinnsyn = GeoInnsynAdapter()
        self._vestfoldkart = VestfoldkartAdapter()

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------
    async def route(
        self,
        municipality_id: str,
        gnr: int | None = None,
        bnr: int | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> RouterResult:
        """
        Fetch planning data for the given property/coordinates and return a
        RouterResult with normalised plans.

        Parameters
        ----------
        municipality_id : str
            4-digit Norwegian kommunenummer, e.g. "5047".
        gnr : int | None
            Gårdsnummer.
        bnr : int | None
            Bruksnummer.
        x : float | None
            UTM33N Easting (used when gnr/bnr are unknown).
        y : float | None
            UTM33N Northing.
        """
        logger.info(
            "[Router] Routing request — municipality=%s gnr=%s bnr=%s x=%s y=%s",
            municipality_id, gnr, bnr, x, y,
        )

        # --- Primary: Kommunekart / arealplaner.no ---
        if municipality_id in KOMMUNEKART_MUNICIPALITIES:
            try:
                plans = await self._kommunekart.fetch_plans(
                    municipality_id, gnr, bnr, x, y
                )
                if plans:
                    return RouterResult(
                        adapter=self._kommunekart.name,
                        municipality_id=municipality_id,
                        gnr=gnr,
                        bnr=bnr,
                        plans=plans,
                    )
                logger.warning(
                    "[Router] KommunekartAdapter returned 0 plans; "
                    "falling through to Planslurpen."
                )
            except NotImplementedError:
                logger.info("[Router] KommunekartAdapter not implemented for this municipality.")
            except Exception as exc:
                logger.warning(
                    "[Router] KommunekartAdapter failed (%s); falling back to Planslurpen.",
                    exc,
                )

        # --- Fallback: Planslurpen ---
        if gnr is not None and bnr is not None:
            try:
                plans = await self._planslurpen.fetch_plans(
                    municipality_id, gnr, bnr, x, y
                )
                return RouterResult(
                    adapter=self._planslurpen.name,
                    municipality_id=municipality_id,
                    gnr=gnr,
                    bnr=bnr,
                    plans=plans,
                )
            except Exception as exc:
                logger.error("[Router] PlanslurpenAdapter also failed: %s", exc)
                return RouterResult(
                    adapter="all_failed",
                    municipality_id=municipality_id,
                    gnr=gnr,
                    bnr=bnr,
                    plans=[],
                    error=str(exc),
                )

        return RouterResult(
            adapter="no_adapter_matched",
            municipality_id=municipality_id,
            gnr=gnr,
            bnr=bnr,
            plans=[],
            error=(
                "Could not find a suitable adapter. "
                "Provide gnr/bnr for Planslurpen fallback, or add the municipality "
                "to KOMMUNEKART_SLUG_MAP."
            ),
        )

    # ------------------------------------------------------------------
    # Convenience wrapper for Flask / Django views
    # ------------------------------------------------------------------
    async def get_plans_json(
        self,
        municipality_id: str,
        gnr: int | None = None,
        bnr: int | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> dict[str, Any]:
        """Return the RouterResult serialised as a plain dict (for JSON responses)."""
        result = await self.route(municipality_id, gnr, bnr, x, y)
        return result.to_dict()


# ---------------------------------------------------------------------------
# Module-level convenience function (backward-compatible with existing code)
# ---------------------------------------------------------------------------

_default_router = MunicipalityRouter()


async def get_planning_data(
    kommune_nr: str,
    gnr: int,
    bnr: int,
    x: float | None = None,
    y: float | None = None,
) -> dict[str, Any]:
    """
    Drop-in replacement for the legacy planslurpen-only get_planning_data().

    Now routes through MunicipalityRouter, which tries KommunekartAdapter
    first and falls back to PlanslurpenAdapter.
    """
    return await _default_router.get_plans_json(
        municipality_id=kommune_nr,
        gnr=gnr,
        bnr=bnr,
        x=x,
        y=y,
    )


# ---------------------------------------------------------------------------
# Built-in test / smoke-test runner
# ---------------------------------------------------------------------------

async def _run_test() -> None:
    """
    Simulate a real request with known test parameters and print the full
    result including all outbound HTTP request details.

    Test case: Malvik (5047), Gnr 61, Bnr 1
    This municipality is served by arealplaner.no (slug: malvik5047).
    """
    print("\n" + "#" * 70)
    print("  BYGGSVAR — Municipality Router Integration Test")
    print("#" * 70)

    test_cases = [
        {
            "label": "Malvik (5047) — Gnr 61, Bnr 1  [Kommunekart primary]",
            "municipality_id": "5047",
            "gnr": 61,
            "bnr": 1,
        },
        {
            "label": "Stavanger (1103) — Gnr 16, Bnr 2784  [Kommunekart primary]",
            "municipality_id": "1103",
            "gnr": 16,
            "bnr": 2784,
        },
        {
            "label": "Unknown municipality (9999) — Gnr 10, Bnr 5  [Planslurpen fallback]",
            "municipality_id": "9999",
            "gnr": 10,
            "bnr": 5,
        },
    ]

    router = MunicipalityRouter()

    for case in test_cases:
        print(f"\n{'~'*60}")
        print(f"  TEST: {case['label']}")
        print(f"{'~'*60}")

        try:
            result = await router.route(
                municipality_id=case["municipality_id"],
                gnr=case.get("gnr"),
                bnr=case.get("bnr"),
            )
            output = result.to_dict()
            print("\n  RESULT (normalised BYGGSVAR JSON):")
            print(json.dumps(output, indent=2, ensure_ascii=False))
        except Exception as exc:
            print(f"\n  ERROR during test: {exc}")

    print("\n" + "#" * 70)
    print("  Test run complete.")
    print("#" * 70 + "\n")


if __name__ == "__main__":
    # Configure a visible console logger so adapter debug prints are visible
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    asyncio.run(_run_test())