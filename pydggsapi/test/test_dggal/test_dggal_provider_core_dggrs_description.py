from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from fastapi.testclient import TestClient
from tinydb import TinyDB
import pytest
from importlib import reload
import os

support_grids = []

db = TinyDB(os.environ.get('dggs_api_config'))
all_dggrs = db.table('dggrs').all()

for dggrs in all_dggrs:
    dggrs_id, dggrs_config = dggrs.popitem()
    if ("dggal_dggrs_provider" in dggrs_config["classname"]):
        support_grids.append(dggrs_id)

assert len(support_grids) > 0


def test_core_dggrs_description():
    import pydggsapi.api
    app = reload(pydggsapi.api).app
    client = TestClient(app)

    for grid in support_grids:
        print(f"Success test case with dggs description {grid}")
        response = client.get(f'/dggs-api/v1-pre/dggs/{grid}')
        assert response.status_code == 200
        assert DggrsDescription(**response.json())

