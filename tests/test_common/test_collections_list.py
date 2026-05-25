from pydggsapi.schemas.ogc_dggs.dggrs_list import DggrsListResponse
from pydggsapi.schemas.api.collections import Collection
from pydggsapi.schemas.ogc_collections.collections import Collections as ogc_Collections
from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
import pytest
from tinydb import TinyDB
from importlib import reload
import os


db = TinyDB(os.environ.get('DGGS_API_CONFIG'))
collections = db.table('collections').all()
collections_dict = {}
for collection in collections:
    cid, collection_config = collection.popitem()
    collection_config['id'] = cid
    collections_dict[cid] = Collection(**collection_config)


def test_list_collections():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)
    print("Success test case with list collections")
    response = client.get('/dggs-api/collections')
    assert response.status_code == 200
    collections = ogc_Collections(**response.json())
    assert len(collections.collections) == len(collections_dict.keys())

