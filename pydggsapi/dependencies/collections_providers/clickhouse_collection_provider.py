from pydggsapi.dependencies.collections_providers.abstract_collection_provider import (
    AbstractCollectionProvider,
    AbstractDatasourceInfo,
    DatetimeNotDefinedError
)
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn, CollectionProviderGetDataDictReturn
from pydggsapi.schemas.ogc_dggs.dggrs_zones import zone_datetime_placeholder

from pygeofilter.ast import AstType
from pygeofilter.ast import Attribute as pygeofilter_ats
from pygeofilter.backends.sql import to_sql_where
from ordered_set import OrderedSet
from dataclasses import dataclass
from clickhouse_driver import Client
from typing import List
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger()


@dataclass
class ClickhouseDatasourceInfo(AbstractDatasourceInfo):
    table: str = "data"
    aggregation: str = "mode"


class ClickhouseCollectionProvider(AbstractCollectionProvider):

    def __init__(self, datasources):
        self.datasources = {}
        if (datasources.get("connection") is None):
            logger.error(f'{__name__} missing db connection info.')
            raise Exception(f'{__name__} missing db connection info.')
        connection = datasources["connection"]
        self.host: str = connection.get("host", "127.0.0.1")
        self.port: int = connection.get("port", 9000)
        self.user: str = connection.get("user", "user")
        self.password: str = connection.get("password", "user")
        self.database: str = connection.get("database", "default")
        self.compression: bool = connection.get("compression", False)
        try:
            self.db = Client(host=self.host, port=self.port, user=self.user, password=self.password,
                             database=self.database, compression=self.compression)
            datasources.pop("connection")
            for k, v in datasources.items():
                self.datasources[k] = ClickhouseDatasourceInfo(**v)
        except Exception as e:
            logger.error(f'{__name__} create datasource failed: {e}')
            raise Exception(f'{__name__} create datasource failed: {e}')

    def get_data(self, zoneIds: List[str], res: int, datasource_id: str,
                 cql_filter: AstType = None, include_datetime: bool = False,
                 include_properties: List[str] = None,
                 exclude_properties: List[str] = None,
                 input_zoneIds_padding: bool = True,
                 collection_timestamp: datetime = None) -> CollectionProviderGetDataReturn:
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} datasource_id not found: {datasource_id}')
            raise Exception(f'{__name__} datasource_id not found: {datasource_id}')
        try:
            res_col = datasource.zone_groups[str(res)]
        except KeyError as e:
            logger.error(f'{__name__} get zone_groups for resolution {res} failed: {e}')
            return result
        incl_cols = OrderedSet(datasource.data_cols)
        if include_properties:
            incl_cols &= set(include_properties)
        if exclude_properties:
            incl_cols -= set(exclude_properties)
        if (datasource.aggregation == 'mode'):
            cols = [f'arrayMax(topK(1)({c})) as {c}' for c in incl_cols]
            cols = ",".join(cols)
        cols += f', {res_col}'
        # cql handling
        query = f'select {cols} from {datasource.table} where {res_col} in (%(cellid_list)s) group by {res_col}'
        if (cql_filter is not None):
            fieldmapping = self.get_datadictionary(datasource_id).data
            fieldmapping = {k: k for k, v in fieldmapping.items()}
            if (include_datetime and datasource.datetime_col is None):
                raise DatetimeNotDefinedError(f"{__name__} filter by datetime is not supported: datetime_col is none")
            if (include_datetime):
                fieldmapping.update({zone_datetime_placeholder: datasource.datetime_col})
            cql_sql = to_sql_where(cql_filter, fieldmapping).replace('"', "")
            query += f' having {cql_sql}'
        try:
            db_result = self.db.execute(query, {'cellid_list': zoneIds}, with_column_types=True)
        except Exception as e:
            logger.error(f'{__name__} get_data failed : {e}')
            raise Exception(f'{__name__} get_data failed : {e}')
        zone_idx = [i for i, r in enumerate(db_result[1]) if (r[0] == res_col)][0]
        if (len(db_result[0]) > 0):
            data = np.array(db_result[0])
            zoneIds = data[:, zone_idx].tolist()
            data = np.delete(data, zone_idx, axis=-1).tolist()
            cols_meta = {r[0]: r[1] for r in db_result[1] if (r[0] != res_col)}
            result.zoneIds, result.cols_meta, result.data = zoneIds, cols_meta, data
        return result

    def get_datadictionary(self, datasource_id: str, include_zone_id: bool = True) -> CollectionProviderGetDataDictReturn:
        try:
            datasource = self.datasources[datasource_id]
        except KeyError:
            logger.error(f'{__name__} datasource_id not found: {datasource_id}')
            raise Exception(f'{__name__} datasource_id not found: {datasource_id}')
        try:
            query = f'DESCRIBE TABLE {datasource.table}'
            db_result = self.db.execute(query)
        except Exception as e:
            logger.error(f'{__name__} get_datadictionary failed : {e}')
            raise Exception(f'{__name__} datasource_id not found: {datasource_id}')
        data = {r[0]: r[1] for r in db_result if (r[0] in datasource.data_cols)}
        if include_zone_id:
            data.update({'zone_id': 'string'})
        return CollectionProviderGetDataDictReturn(data=data)
