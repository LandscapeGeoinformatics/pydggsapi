Zarr Collection Provider
==============================

The implementation uses `xarray.Datatree <https://docs.xarray.dev/en/latest/generated/xarray.DataTree.html>`_ as the driver to access Zarr data. The provider serves multiple Zarr data sources. At the initialisation stage, it loads the ``datasources`` to get each Zarr data configuration, then it creates an xarray datatree handler for each of them and stores it under ``self.datasources`` with the id as the key.

Each group of the Zarr data source represents data from the same refinement level, with zone IDs as the index. Here is an example of how Zarr data is organised. 

|zarr_data_example|

ZarrDatasourceInfo
------------------

- ``filepath`` : String. A file path of the data source. Supports both local, gcs and s3 cloud storage.
- ``id_col``: String. The column name of the zone IDs, default is "".
- ``filehandle``: xarray datatree object to store the connection.


Class initialisation
--------------------

The dictionary ``datasources`` contains information about one or more Zarr data sources in the form of a child dictionary. The key of the child dictionary represents the unique ID for the Zarr data. Currently, only local storage is supported.

An example to define a Zarr collection provider:

.. code-block:: json

    "collection_providers": {"1": 
            {"zarr": 
                {"classname": "zarr_collection_provider.ZarrCollectionProvider", 
                    "datasources": {
                           "my_zarr_data": {
                                "filepath": "<path to zarr folder>",
                                "id_col": "zoneId",
                                 "zones_grps" : { "4": "res4", "5": "res5"}
                            } 
                        } 
                    }
            }
    }

   

.. |zarr_data_example| image:: ../../../images/zarr_data_example.png
   :width: 600
