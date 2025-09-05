from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint


def test_core_dggs_list_empty_config():
    os.environ['dggs_api_config'] = './empty.json'
    try:
        import pydggsapi.api
        app = reload(pydggsapi.api).app
        client = TestClient(app)
    except Exception as e:
        print(f"Testing with dggs-list (no dggrs defined): {e}")


def test_core_dggs_list():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
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
    response = client.get('/dggs-api/v1-pre/collections/hytruck/dggs')
    pprint(response.text)
    assert "hytruck not found" in response.text
    assert response.status_code == 400

    print("Success test case with collections dggs-list (suitability_hytruck)")
    response = client.get('/dggs-api/v1-pre/collections/suitability_hytruck/dggs')
    pprint(response.json())
    assert DggrsListResponse(**response.json())
    assert response.status_code == 200








