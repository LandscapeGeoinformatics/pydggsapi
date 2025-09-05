from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint


def test_core_dggs_description_empty_config():
    os.environ['dggs_api_config'] = './empty.json'
    try:
        import pydggsapi.api
        app = reload(pydggsapi.api).app
        client = TestClient(app)
    except Exception as e:
        print(f"Testing with dggrs definition (no dggrs defined): {e}")


def test_core_dggrs_description():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/v1-pre/dggs/Not_exisits')
    pprint(response.json())
    assert "not supported" in response.text
    assert response.status_code == 400

    os.environ['dggs_api_config'] = './dggs_api_config.json'
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Success test case with dggs description (igeo7)")
    response = client.get('/dggs-api/v1-pre/dggs/igeo7')
    pprint(response.json())
    assert DggrsDescription(**response.json())
    assert response.status_code == 200

    # Fail Case on Collection Not found
    print("Fail test case with collections dggs-description (collection not found)")
    response = client.get('/dggs-api/v1-pre/collections/hytruck/dggs/igeo7')
    pprint(response.text)
    assert "hytruck not found" in response.text
    assert response.status_code == 400

    print("Fail test case with collections dggs-description (non-existing dggrs id)")
    response = client.get('/dggs-api/v1-pre/collections/suitability_hytruck/dggs/Non_existing')
    pprint(response.text)
    assert "not supported" in response.text
    assert response.status_code == 400

    print("Success test case with collections dggs-description (suitability_hytruck, igeo7)")
    response = client.get('/dggs-api/v1-pre/collections/suitability_hytruck/dggs/igeo7')
    pprint(response.json())
    assert DggrsDescription(**response.json())
    assert response.status_code == 200

    print("Success test case with collections dggs-description (suitability_hytruck, h3)")
    response = client.get('/dggs-api/v1-pre/collections/suitability_hytruck/dggs/h3')
    pprint(response.json())
    assert DggrsDescription(**response.json())
    assert response.status_code == 200
