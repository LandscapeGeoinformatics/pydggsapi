Clickhouse Collection Provider
==============================
The implementation uses `clickhouse_drive <https://clickhouse-driver.readthedocs.io/en/latest/>`_  to connect to Clickhouse DB. The provider serves multiple tables on the same database, with each table as a data source. It creates an instance of ``clickhouse_diver::Client`` at initialisation and assigns it to ``self.db``. The reference is used in ``get_data`` for data queries. 

ClickhouseDatasourceInfo
------------------------

- ``table``: A string to indicate the table for query
- ``aggregation``: A string to indicate which aggregation should use. Currently only for `mode`.

Note on Clickhouse query
-------------------------
Clickhouse restricts the query size to 200KB by default. It is controlled by the setting `max_query_size <https://clickhouse.com/docs/operations/settings/settings#max_query_size>`_ . The default size is too small when the number of zone IDs for the query is large. For instance, each zone ID consumes 10 bytes for IGEO7 z7 (in string format) at refinement level 8, the query is limited to 20,000 zones without considering other overheads.


Class initialisation
--------------------

Clickhouse prvoider need an extra setting "connection" from the ``datasources`` to define the DB connection:

.. code-block:: json
    "connection" {
        "host": "127.0.0.1",
        "user": "default",
        "password": "default",
        "port": 9000
        "compression": False,
        "database": "default"
    }

An example to define a Clickhouse collection provider:

.. code-block:: json

     "collection_providers": {
        "1": {
        "clickhouse": {
            "classname": "clickhouse_collection_provider.ClickhouseCollectionProvider",
            "datasources": {
        	    "connection": {
        		    "host": "127.0.0.1",
          		    "user": "default",
                    "password": "user",
          		    "port": 9000,
          		    "database": "DevelopmentTesting"
        	    },
        	    "hytruck_clickhouse": {
            	    "table": "testing_suitability_IGEO7",
            	    "zone_groups": {
                            "9": "res_9_id",
                            "8": "res_8_id",
                            "7": "res_7_id",
                            "6": "res_6_id",
                            "5": "res_5_id"
                    },
                    "data_cols": ["data_1", "data_2"]
         	        }
                }
            }
        }
    }
    

