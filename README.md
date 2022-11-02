# Camunda/Zeebe wrapper

The Camunda/Zeebe wrapper converts the Zeebe gRPC API into a simpler REST-API. It also focus on functions that are performed by JavaScript code in Optimizely and logically works as the link between the UI and the business logic and the underlying production systems.

It consist of two main functions:
* An API to start a workflow (a Zeebe process).
* An API to perform singel functions like send an e-mail, retrieve value lists for the UI or send data from and to backoffice systems.

## Start a workflow

You start a workflow by calling the wrapper with:

```
curl -X POST -d '<JSON-struct>' -H "Content-Type: application/json" https://<camunda-url>/workflow/<workflowname>?<query_args>
```

The call takes both query_args and a JSON body. All values are sent to Zeebe as start parameters for the process. The workflow name (the process ID in Zeebe) is the the "workflow-name" parameter and must match an existing process in Zeebe.

The content of query_args and the JSON body is interpreted by the actions in the workflow. The wrapper only passes these on to the process. Apart from the "userid" parameter (see below) there is no common interpretation of the parameters.

The workflow call has the following HTTP response status codes:
- 200: Process is started. A JSON is returned, {'processID':processInstanceKey}, where 'processID' is the ID of the just started process. The 'processID' value is just for trouble shooting purposes and there is currently no use of this value for the UI.
- 404: The \<workflowname\> process does not exist in Zeebe.
- 503: Zeebe engine is not available
- 500: An unknown error has occured.

## Start a worker (a single action)

The call is similar to the workflow call, but instead of a complete workflow a single Camunda worker is started and the result of the worker is returned to the caller. If no result is returned after 60 second, a timeout occurs in the wrapper.

```
curl -X [GET,POST,PATCH] [-d '<JSON-struct>' -H "Content-Type: application/json"] https://<camunda-url>/worker/<workername>?<query_args>
```

The call takes both query_args and an optional JSON body. All values, together with HTTP method, are sent to Zeebe as start parameters for the process. The \<worker\>" parameter must match an existing worker name that is deployed in Zeebe.

The content of query_args, the JSON body and the HTTP method used, is interpreted by the worker. The wrapper only passes these on to the worker. Apart from the "userid" parameter (see below) there is no common interpretation of the parameters. Any result from a worker execution is passed back as a result from the call.

What parameters a specific worker use and what is returned, is documented in each worker documentation.

The workflow call has the following HTTP response status codes:
- 200: All is good and the result of the worker is returned.
- 400: The worker returned an error. The error is returned as text.
- 404: The "worker" does not exist in Zeebe.
- 408: The worker didn't respond within the required time limit.
- 503: Zeebe engine is not available
- 500: An unknown error has occured.

## The "userid" parameter

The "userid" parameter is a special parameter that needs to be included in most worker and workflow calls. It's is interpreted as the identity of the user that is using the UI that performes the call. When the UI app is hosted in Optimizely, this parameter is automatically set to the user ID of the user that is authencicated (logged in) in the portal. It's a personnummer for external users and the AD ID for internal users. If no user is authenticated, Optimizely passes on an empty value.

The UI app should never set this parameter in a call and if it does, it's value is overridden by Optimizely.

