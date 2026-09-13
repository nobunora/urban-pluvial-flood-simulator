"""Geocoding API routes."""

from __future__ import annotations

from fastapi import APIRouter

from floodsim.api.errors import ApiContractError
from floodsim.api.schemas import (
    GeocodeAttribution,
    GeocodeCandidateResponse,
    GeocodeResponse,
)
from floodsim.providers.common import ProviderError
from floodsim.providers.geocoder import CsisSimpleGeocoder

router = APIRouter()
geocoder = CsisSimpleGeocoder()


@router.get("/geocode", response_model=GeocodeResponse)
def geocode(q: str) -> GeocodeResponse:
    query = q.strip()
    if not query:
        raise ApiContractError(400, "INPUT_EMPTY_GEOCODE_QUERY", "検索語を入力してください。")
    if len(query) > 200:
        raise ApiContractError(400, "INPUT_GEOCODE_QUERY_TOO_LONG", "検索語は200文字以内で入力してください。")
    try:
        result = geocoder.search(query)
    except ProviderError as exc:
        raise ApiContractError(
            503,
            "GEOCODER_UNAVAILABLE",
            "住所・地名検索を利用できません。",
            retryable=exc.retryable,
        ) from exc
    return GeocodeResponse(
        candidates=[GeocodeCandidateResponse.model_validate(candidate.__dict__) for candidate in result.candidates],
        attribution=GeocodeAttribution(text=result.attribution_text, url=result.attribution_url),
    )
