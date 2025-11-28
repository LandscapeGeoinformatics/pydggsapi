from pydggsapi.schemas.api.collections import Collection

from tinydb import TinyDB
import logging
import os

logger = logging.getLogger()


def get_collections_info() -> dict[str, Collection]:
    db = TinyDB(os.environ.get('dggs_api_config'))
    if ('collections' not in db.tables()):
        logger.error(f'{__name__} collections table not found.')
        raise Exception(f'{__name__} collections table not found.')
    collections = db.table('collections').all()
    if (len(collections) == 0):
        logger.warning(f'{__name__} no collections defined.')
        # raise Exception(f'{__name__} no collections defined.')
    collections_dict = {}
    for collection in collections:
        cid, collection_config = collection.popitem()
        collection_config['id'] = cid
        collections_dict[cid] = Collection(**collection_config)
    return collections_dict
