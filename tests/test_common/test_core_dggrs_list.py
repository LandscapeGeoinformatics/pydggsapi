from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint


def test_core_dggs_list():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Success test case with dggs-list")
    response = client.get('/dggs-api/v1-pre/dggs')
    pprint(response.json())
    assert DggrsListResponse(**response.json())
    assert response.status_code == 200

    # Fail Case on Collection Not found
    print("Fail test case with collections dggs-list (collection not found)")
    response = client.get('/dggs-api/v1-pre/dggs/not_exist')
    pprint(response.text)
    assert "not support" in response.text
    assert response.status_code == 400







