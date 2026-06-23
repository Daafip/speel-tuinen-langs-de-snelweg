import pytest

from restspots.config import get_country, load_countries


def test_load_countries_has_de():
    countries = load_countries()
    assert "DE" in countries
    de = countries["DE"]
    assert de.iso == "DE"
    assert de.stop_tags["highway"] == ["services", "rest_area"]
    assert "autobahn_api" in de.enrichment


def test_get_country_case_insensitive():
    assert get_country("de").iso == "DE"


def test_get_country_unknown_raises():
    with pytest.raises(KeyError):
        get_country("ZZ")
