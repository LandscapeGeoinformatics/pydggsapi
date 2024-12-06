from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from fastapi.testclient import TestClient
from importlib import reload
import pydggsapi.api
import os


def test_core_dggs_list_empty_config():
    os.environ['dggs_api_config'] = './empty.json'
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Testing with dggs-list (no dggrs defined)")
    response = client.get('/dggs-api/v1-pre/dggs')
    print(response.text)
    assert "No dggrs definition is found" in response.text
    assert response.status_code == 500


def test_core_dggs_list():
    os.environ['dggs_api_config'] = './dggs_api_config.json'
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Success test case with dggs-list")
    response = client.get('/dggs-api/v1-pre/dggs')
    print(response.json())
    assert DggrsListResponse(**response.json())
    assert response.status_code == 200

    # Fail Case on Collection Not found
    print("Fail test case with collections dggs-list (collection not found)")
    response = client.get('/dggs-api/v1-pre/collections/hytruck/dggs')
    print(response.text)
    assert "hytruck not found" in response.text
    assert response.status_code == 500

    print("Success test case with collections dggs-list (suitability_hytruck)")
    response = client.get('/dggs-api/v1-pre/collections/suitablilty_hytruck/dggs')
    print(response.json())
    assert DggrsListResponse(**response.json())
    assert response.status_code == 200