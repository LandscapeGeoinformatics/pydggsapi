from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.api.collections import Collection
from fastapi.testclient import TestClient
import pytest
from tinydb import TinyDB
from importlib import reload
import os
from pprint import pprint

db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collections_dict = {}
for collection in collections:
    cid, collection_config = collection.popitem()
    if (collection_config['collection_provider']['dggrsId'] == 'igeo7'):
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)


def test_core_dggrs_description():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Fail test case with non existing dggrs id")
    response = client.get('/dggs-api/dggs/Not_exisits')
    pprint(response.json())
    assert "not supported" in response.text
    assert response.status_code == 400

    print("Success test case with dggs description (igeo7)")
    response = client.get('/dggs-api/dggs/igeo7')
    pprint(response.json())
    assert DggrsDescription(**response.json())
    assert response.status_code == 200

    # Fail Case on Collection Not found
    print("Fail test case with collections dggs-description (collection not found)")
    response = client.get('/dggs-api/collections/not_exist/dggs/igeo7')
    pprint(response.text)
    assert "not_exist not found" in response.text
    assert response.status_code == 404

    for collection_name, collection in collections_dict.items():
        dggrsId = collection.collection_provider.dggrsId
        print("Fail test case with collections dggs-description (not exist dggrs id)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/not_exist')
        pprint(response.text)
        assert "not supported" in response.text
        assert response.status_code == 400
        print(f"Success test case with collections dggs-description ({collection_name}, {dggrsId})")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/{dggrsId}')
        pprint(response.json())
        assert DggrsDescription(**response.json())
        assert response.status_code == 200

        print(f"Success test case with collections dggs-description ({collection_name}, h3)")
        response = client.get(f'/dggs-api/collections/{collection_name}/dggs/h3')
        pprint(response.json())
        assert DggrsDescription(**response.json())
        assert response.status_code == 200
