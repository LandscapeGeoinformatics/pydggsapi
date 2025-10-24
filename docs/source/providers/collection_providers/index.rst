Abstract Datasource Info
========================

For each Collection Provider, it must have its own DatasourceInfo class that extends from the AbstractDatasourceInfo. The abstract class holds the standardised data source info. The API doesn't directly interact with the data source info; it is mainly used by the ``get_data`` function of the collection provider.

Each data source defined under the ``collection_providers`` is instantiated as the corresponding data source info class when loaded. All data sources are stored in the `datasources` dictionary of the collection provider.

The attributes of Abstract Datasource Info class are: 

- ``data_cols``: a list of column names(in string) used to ``get_data``, default to:  ['*'] , which means all columns.
- ``exclude_data_cols``: a list of column names(in string) that are excluded from ``get_data``, default to:  [].
- ``datetime_col``: a string of column name to specify the datetime column of the datasource. default to ``None``.
- ``zone_groups`` : A dictionary to map the refinement level to the column name that stores the zone IDs.




Abstract Collection providers
=============================

To implement a collection provider, users need to provide initialisation of the ``datasources`` variable and the implementation of the interfaces listed below:

Variable:

- ``datasources``: a dictionary with key equals to the ``datasource_id`` that map to the correspodning datasource info class.

Interfaces: 

- ``get_data``: implementation of the data query from the dataset
- ``get_datadictionary``: implementation of getting the data dictionary (column names and data types) from the dataset, for the tiles JSON response.

Class initialisation
--------------------

The :ref:`collection_providers <collection_providers>` must initialise the ``datasources`` dictionary of the class with the ``datasources`` configuration from the ``collection_providers`` table. Users can reference the full example :ref:`here <_collection_provider_config_example>`.

For example, the ``ParquetDatasourceInfo`` and the ``datasources`` configuration:

.. code-block:: python

   class ParquetDatasourceInfo(AbstractDatasourceInfo):
    filepath: str = ""
    id_col: str = ""
    conn: duckdb.DuckDBPyConnection = None


.. code-block:: json

    "hytruck_local": {
        "filepath": "~/file_path/igeo7_4-10.parquet",
	    "id_col": "cell_ids",
	    "data_cols": ["stations_band_1", "pipelines_band_1","pipelines_band_2"],
		"exclude_data_cols": ["geometry"]
	}
    

.. _parameters_for_get_data:

Parameters for get_data
-----------------------

The pydggsapi creates collection provider objects at the beginning, and data sources that share the same provider will use the same object instance. The ``get_data`` function accepts five parameters:

- ``zoneIds``: A list of zone IDs for retrieving the data at specific zones 
- ``res``: refinement level 
- ``datasource_id``: defined in each :ref:`collection providers <collection_providers>` to retrieve the corresponding data source info class, which is used to perform queries.
- ``cql_filter``: a `pygeofilter <https://github.com/geopython/pygeofilter>`_ parser object for CQL2 query handling.
- ``include_datetime``: a boolean to indicate if the ``cql_filter`` consist of datetime query

Temporal data source:

The implementation should check if the ``datetime_col`` is set inside the  data source info if ``include_datetime`` is True. Then, it should map the ``zone_datetime_placeholder`` (defined inside schemas/ogc_dggs/dggrs_zones.py) to the column name specified by ``datetime_col`` using the fieldmapping from ``pygeofilter``.


Parameters for get_datadictionary
---------------------------------
The pydggsapi passes in the ``getdata_params`` to this function, so developers can reuse the parameters to determine which data source should be used to provide the data dictionary.

.. _collection_providers_implementation:

Implementations
---------------
.. toctree::
   :glob:
   :titlesonly:

   implementations/*








