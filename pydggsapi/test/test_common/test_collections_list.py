from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
import pytest
from importlib import reload
import os
from pprint import pprint


def test_list_collections():
    os.environ['dggs_api_config'] = './dggs_api_config_testing.json'
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Success test case with list collections")
    response = client.get('/dggs-api/v1-pre/collections')
    pprint(response.json())
    assert response.status_code == 200







