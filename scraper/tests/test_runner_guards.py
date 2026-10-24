import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from metro.extraction import Restricted, ExtractionError
from metro.scraper import check_access, Config

def test_configuration_limits():
    for values in ({'concurrency':9},{'delay':0},{'retries':10},{'url':'https://other.com'}):
        with pytest.raises(ValueError): Config(**values).validate()

def test_blocked_response_stops_before_parsing():
    page=MagicMock()
    response=MagicMock(status=403)
    with pytest.raises(Restricted): asyncio.run(check_access(page,response))
    page.title.assert_not_called()

def test_visible_challenge_and_normal_recaptcha_script():
    page=MagicMock()
    page.title=AsyncMock(return_value='Apartamento')
    page.locator.return_value.inner_text=AsyncMock(return_value='Datos del inmueble')
    page.locator.return_value.filter.return_value.count=AsyncMock(return_value=0)
    asyncio.run(check_access(page))
    page.locator.return_value.filter.return_value.count=AsyncMock(return_value=1)
    with pytest.raises(Restricted): asyncio.run(check_access(page))

def test_http_failure_not_treated_as_empty_property():
    with pytest.raises(ExtractionError): asyncio.run(check_access(MagicMock(),MagicMock(status=404)))
