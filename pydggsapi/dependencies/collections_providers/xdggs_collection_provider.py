from pydggsapi.dependencies.collections_providers.zarr_collection_provider import ZarrCollectionProvider, ZarrDatasourceInfo
from pydggsapi.schemas.api.collection_providers import CollectionProviderGetDataReturn, CollectionProviderGetDataDictReturn

import xarray as xr
import xdggs
import logging
from pygeofilter.ast import AstType
from datetime import datetime
from typing import List, Any, Dict
from dataclasses import dataclass

logger = logging.getLogger()


def _legacy_convertor_translator(dggs_attribute: Dict[str, str]) -> (str, str, Dict[str, str]):
    dggs = dggs_attribute.copy()
    if (dggs.get("name")):
        dggs.update({"grid_name": dggs.pop("name")})
    if (dggs.get("refinement_level")):
        dggs.update({"level": dggs.pop("refinement_level")})
    compression = dggs.pop("compression")
    id_col = dggs.pop("coordinate")
    dggs.pop("spatial_dimension")
    return id_col, compression, dggs


@dataclass
class XdggsDatasourceInfo(ZarrDatasourceInfo):
    index_kind: str = None
    compression: str = "none"


# xdggs provider inhert from ZarrCollectionProvider
class XdggsCollectionProvider(ZarrCollectionProvider):

    def __init__(self, datasources):
        self.datasources = {}
        try:
            for k, v in datasources.items():
                zones_group = {}
                datasource = XdggsDatasourceInfo(**v)
                dt = xr.open_datatree(datasource.filepath, engine="zarr", chunks="auto",
                                      storage_options=datasource.storage_options, consolidated=False)
                id_col = datasource.id_col
                # we need a new datatree to hold the xdggs dataset
                new_dt = xr.DataTree(name=k)
                skip = [True] * len(dt.groups)
                group_id_col = ""
                for i, group in enumerate(dt.groups):
                    if (group != "/"):
                        ds = dt[group].to_dataset()
                        group_name = group[1:]
                        # if id_col is not specify, try to get dggs attribute from the dataset.attrs
                        # otherwise, assume it is under the variabel id_col's attrs
                        if (id_col == ""):
                            # check if the dggs attribute is in the dataset attribute
                            if (ds.attrs.get("dggs", None) is None):
                                # dggs attribute not found, skip the whold datasource
                                logger.warning(f'{__name__} can\'t locate the dggs attribute in {k} for group: {group}')
                                continue
                            else:
                                # if dggs attribute exists in dataset attribute, copy it to the id_col variable
                                group_id_col, datasource.compression, dggs_attrs = _legacy_convertor_translator(ds.attrs["dggs"])
                                ds[group_id_col].attrs.update(dggs_attrs)
                        try:
                            ds = xdggs.decode(ds, index_options={"index_kind": datasource.index_kind})
                                                                # "compression": datasource.compression})
                            new_dt[group_name] = xr.DataTree(dataset=ds)
                            zones_group[str(ds.dggs.grid_info.level)] = group_name
                            skip[i] = False
                            # new_dt = new_dt.assign({group_name: xr.DataTree(dataset=ds)})
                        except Exception as e:
                            logger.warning(f'{__name__} error when decoding {group} in {k} to xdggs: {e} , skipped.')
                            continue
                # skip adding the datasource if all groups failed from decode as xdggs dataset
                if (not all(skip)):
                    datasource.zone_groups = zones_group
                    datasource.filehandle = new_dt
                    if datasource.id_col == "":
                        datasource.id_col = group_id_col
                    self.datasources[k] = datasource
                    logger.info(f"{__name__} added datasource: {k}")
        except Exception as e:
            logger.error(f'{__name__} create datasource failed: {e}')
            raise Exception(f'{__name__} create datasource failed: {e}')

    def get_data(self, zoneIds: List[Any], res: int, datasource_id: str,
                 cql_filter: AstType = None, include_datetime: bool = False,
                 include_properties: List[str] = None,
                 exclude_properties: List[str] = None,
                 input_zoneIds_padding: bool = True,
                 collection_timestamp: datetime = None,
                 check_if_exists_only: bool = False) -> CollectionProviderGetDataReturn:
        # since xarray-sql doesn't work with xdggs xindexes,
        # I have to change it back to a normal dataset when the cql_filter is not None
        print("Xdggs get_data call")
        result = CollectionProviderGetDataReturn(zoneIds=[], cols_meta={}, data=[])
        datasource = self.datasources[datasource_id]
        datatree = datasource.filehandle
        try:
            group_name = datasource.zone_groups[str(res)]
        except KeyError as e:
            logger.error(f'{__name__} get zone_grp for resolution {res} failed: {e}')
            return result
        target_ds = datatree[group_name].to_dataset()
        index_type = type(target_ds.xindexes.get(datasource.id_col))
        restore = False
        if (cql_filter is not None and (not isinstance(index_type, xr.core.indexes.PandasIndex))):
            print("Xdggs handling ")
            target_ds = target_ds.drop_indexes(datasource.id_col)
            self.datasources[datasource_id].filehandle = datatree.assign({group_name: xr.DataTree(dataset=target_ds)})
            restore = True

        print("Xdggs parent get_data call")
        result = super().get_data(zoneIds, res, datasource_id, cql_filter, include_datetime,
                                  include_properties, exclude_properties, input_zoneIds_padding,
                                  collection_timestamp, check_if_exists_only)
        if (restore):
            print("Xdggs rollback ")
            target_ds = xdggs.decode(target_ds, index_options={"index_kind": datasource.index_kind,
                                                               "compression": datasource.compression})
            self.datasources.filehandle[group_name[1:]] = xr.DataTree(dataset=target_ds)
        return result
