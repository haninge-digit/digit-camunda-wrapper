# Camunda/Zeebe wrapper

The Camunda/Zeebe wrapper converts the Zeebe gRPC API into a simpler REST-API. It also focus on functions that are performed by (jacaScript) code in Optimizely and logically works as the link between the UI and the underlying production systems.


It consist of three main functions:
* An API to start a workflow (a Zeebe process).
* An API to retrieve and send data from and to backoffice systems.
* An API to handle user tasks.

## Start a workflow

You start a workflow by calling the wrapper with:

```
curl -X POST [-d '<JSON-struct>' -H "Content-Type: application/json"] https://<camunda-url>/workflow/<workflow-name>?<query args>
```

The call takes both query_args and a JSON body. All values are combined and sent to Zeebe as separate parameters. The workflow name (the process ID in Zeebe) is the the "workflow-name" parameter and must match an existing process in Zeebe.

HTTP response status codes:
- 200: Process is started. A JSON is returned, {'processID':processInstanceKey}, where 'processID' is the ID of the just started process. There is current nu possible use of this value for the UI.
- 404: The "workflow-name" process does not exist in Zeebe.
- 503: Zeebe engine is not available
- 500: An unknown error has occured.

## Start a worker (a system integration)

The call is similar to the workflow call, but instead of a complete workflow a single Camunda worker is started and the result of the worker is returned to the caller. If no result is returned after 30 second, an 50 is returned.

```
curl -X GET https://<camunda-url>/worker/<worker-name>?<query args>
```

The call returns a JSON-stucture with the values the worker returned. The exact content and the interpretation of this content is a contract between the UI and the worker.

HTTP response status codes:
- 200: All is good.
- 400: The worker returned an error. The error is returned as text.
- 404: The "worker" does not exist in Zeebe.
- 408: The worker didn't respond within the required time limit.
- 503: Zeebe engine is not available
- 500: An unknown error has occured.

## Handle user tasks

```
curl -X [GET,POST] https://<camunda-url>/task/<task_id>?<query args>
```

*Documentation to be included here.*
