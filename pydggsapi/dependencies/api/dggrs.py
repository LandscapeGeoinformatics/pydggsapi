from pydggsapi.schemas.ogc_dggs.dggrs_descrption import DggrsDescription
from pydggsapi.schemas.ogc_dggs.common_ogc_dggs_api import Link
from pydggsapi.dependencies.api.collections import get_collections_info

from typing import Any, Dict, Tuple
from tinydb import TinyDB
import logging
import os

logger = logging.getLogger()


def get_conformance_classes():
    return [
        "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
        "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/landing-page",
        "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/json",
        # "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/html",
        # technically OAS 3.1 used here, but OGC still catching up...
        # (https://github.com/opengeospatial/ogcapi-common/issues/208)
        "https://www.opengis.net/spec/ogcapi-common-1/1.0/conf/oas30",
        "https://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
        "https://www.opengis.net/spec/ogcapi-common-2/1.0/conf/umd-collection",
        "https://www.opengis.net/spec/ogcapi-common-3/1.0/conf/queryables",
        "https://www.opengis.net/spec/ogcapi-common-3/1.0/conf/returnables-and-receivables",
        "https://www.opengis.net/spec/ogcapi-common-3/1.0/conf/schemas",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/core",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/root-dggs",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/collection-dggs",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/zone-query",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/zone-query-cql2-filter",
        # "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/zone-unit64",  # application/x-binary zone-list
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/zone-geojson",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-custom-depths",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-retrieval",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-cql2-filter",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-json",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-ubjson",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-geojson",
        "https://www.opengis.net/spec/ogcapi-dggs-1/1.0/conf/data-zarr",
    ]


def _checkIfTableExists() -> TinyDB:
    db = TinyDB(os.environ.get('dggs_api_config'))
    if ('dggrs' not in db.tables()):
        logger.error(f"{__name__} dggrs table not found.")
        raise Exception(f"{__name__} dggrs table not found.")
    return db


def get_dggrs_class(dggrsId: str) -> Tuple[str, Dict[str, Any]]:
    try:
        db = _checkIfTableExists()
    except Exception as e:
        logger.error(f"{__name__} {e}")
        raise Exception(f"{__name__} {e}")
    dggrs_indexes = db.table('dggrs')
    for dggrs in dggrs_indexes:
        id_, dggrs_config = dggrs.popitem()
        if (id_ == dggrsId):
            return (dggrs_config['classname'], dggrs_config.get('parameters', {}))
    return None


def get_dggrs_descriptions() -> Dict[str, DggrsDescription]:
    try:
        db = _checkIfTableExists()
        collections = get_collections_info()
    except Exception as e:
        logger.error(f"{__name__} {e}")
        raise Exception(f"{__name__} {e}")
    if (len(collections.keys()) == 0):
        logger.error(f"{__name__} no collections found")
        raise Exception(f"{__name__} no collections found")
    dggrs_indexes = db.table('dggrs').all()
    if (len(dggrs_indexes) == 0):
        logger.error(f"{__name__} no dggrs defined.")
        raise Exception(f"{__name__} no dggrs defined.")
    dggrs_dict = {}
    collection_providers = [v.collection_provider for k, v in collections.items()]
    max_dggrs = {}
    for cp in collection_providers:
        try:
            current_max = max_dggrs[cp.dggrsId]
            max_dggrs[cp.dggrsId] = cp.max_refinement_level if (current_max < cp.max_refinement_level) else current_max
        except KeyError:
            max_dggrs[cp.dggrsId] = cp.max_refinement_level
    for dggrs in dggrs_indexes:
        dggrsid, dggrs_config = dggrs.popitem()
        dggrs_def = dggrs_config['definition_link'] or f'[ogc-dggrs:{dggrsid}]'
        self_link = Link(
            href='',
            type='application/json',
            rel='self',
            title='DGGRS description link',
        )
        dggrs_model_link = Link(
            href=dggrs_def,
            rel='[ogc-rel:dggrs-definition]',
            title='DGGRS definition',
        )
        dggrs_config['id'] = dggrsid
        dggrs_config['uri'] = dggrs_def
        dggrs_config['maxRefinementLevel'] = max_dggrs.get(dggrsid, 32)
        dggrs_config['links'] = [self_link, dggrs_model_link]
        del dggrs_config['definition_link']
        dggrs_dict[dggrsid] = DggrsDescription(**dggrs_config)
    return dggrs_dict
