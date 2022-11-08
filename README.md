# OnDemand Semantic Connector

The OnDemand Semantic Connector allows to generate Knowledge Graphs on demand by receiving REST API calls. The generated Knowledge Graph will upload immediately to a HDFS data storage.

## Execution of the API

For the activation of the API the following command must be used:

```
python app.py
```

The API allows for the execution of the Connector. To execute the Connector, the following API call must be used:

```
0.0.0.0:4000/graph_creation/<path:remove_duplicate>
```

Where `<path:remove_duplicate>` can be replaced by either "yes" or "no". Where the "yes" option indicates that the duplicates must be removed from the Knowledge Graph. For purpose of testing the Connector, sample data is provided in the `engiedata` folder.

## Execution of HDFS

A docker container with an HDFS image is provided for the execution of the Connecter. To make the HDFS storage space run the following command must be executed in the `hadoop` folder.
 
```
docker-compose --file docker-compose-hdfs.yml
```

By accesing `0.0.0.0:8088/filebrowser`, the HDFS image user interface can be accessed. 