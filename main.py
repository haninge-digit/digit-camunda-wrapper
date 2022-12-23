# digit-camunda-wrapper
#
# This is a REST and convinience API that wraps Camunda gRPC API
# 

import os
import multiprocessing
import uuid
import logging
import json
import time


import sanic
from motor.motor_asyncio import AsyncIOMotorClient

import grpc
from zeebe_grpc import gateway_pb2_grpc
from zeebe_grpc.gateway_pb2 import (
    CreateProcessInstanceRequest,
    CreateProcessInstanceWithResultRequest,
    ActivateJobsRequest,
    CompleteJobRequest,
    TopologyRequest)

# from auth import protected


""" 
Environment
"""
ZEEBE_ADDRESS = os.getenv('ZEEBE_ADDRESS',"camunda8-zeebe-gateway:26500")   # Zeebe address and port
MONGO_ROOT_PWD = os.getenv('MONGO_ROOT_PWD')                              # MONGO_DB root password (no default)
MONGO_HOST = os.getenv('MONGO_HOST', "mongodb.mongodb:27017")

DEBUG_MODE = os.getenv('DEBUG','false') == "true"                           # Enable global DEBUG logging
DEV_MODE = os.getenv('DEV_MODE','false') == "true"                          # Sanic develpoment mode

# JWT_SECRET = os.getenv('JWT_SECRET',None)                                   # Secret (!!!) for JWT generation and verification
DISABLE_AUTH = os.getenv('DISABLE_AUTH','false') == "true"                  # Disable API authentication for testing purposes
DISABLE_TASK_API = os.getenv('DISABLE_TASK_API','false') == "true"          # Disable wrapper task API for testing purposes

MAX_TIME_WORKER = 60                                                        # Max time in seconds to wait for a worker to return result
LOGFORMAT = "%(asctime)s %(funcName)-10s [%(levelname)s] %(message)s"       # Log format


""" 
Sanic app instance
"""
app = sanic.Sanic("Camunda_Wrapper")       # A Sanic instance


""" 
Server startup and shutdown functions
"""
@app.before_server_start
def startup(app, loop):
    logging.info("Starting Camunda Wrapper")
    # app.ctx.jwt_secret = JWT_SECRET
    # app.ctx.disable_auth = DISABLE_AUTH
    app.ctx.running = True
    app.ctx.channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
    app.ctx.stub = gateway_pb2_grpc.GatewayStub(app.ctx.channel)

@app.after_server_stop
def shutdown(app, loop):
    logging.info("Stopping Camunda Wrapper")
    app.ctx.running = False
    # app.ctx.channel.close()   # Can't do close() here! Can be skipped?


""" 
Worker API
This API calls a single Camunda worker and returns the result from that worker.
The API passes on the HTTP-method that calls the API.
If a json-body is present in the call, it is passed on as a single valirable, _JSON_BODY

All returned results are in JSON format.
"""
@app.route("/worker/<worker_name:str>", methods=['GET', 'PUT', 'POST', 'PATCH', 'DELETE'])
# @protected      # API requires a valid JWT token
async def start_worker(request, worker_name:str):
    stub = request.app.ctx.stub

    params = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
    params['_HTTP_METHOD'] = request.method  # Pass request method
    # params['HTTP_METHOD'] = request.method  # Old style
    if request.json:
        params['_JSON_BODY'] = json.dumps(request.json)     # Add JSON-body if it exists
    userid = params.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Worker call start. Loggid = {logg_id:>10};  Worker = {worker_name};  userID = {userid}")
        worker_process = f"{worker_name}_worker"        # The ID of the worker is now suffixed with "_worker"   **NEW!**
        cpir = CreateProcessInstanceRequest(bpmnProcessId=worker_process, version=-1, variables=json.dumps(params))
        cpiwrr = CreateProcessInstanceWithResultRequest(request=cpir, requestTimeout=MAX_TIME_WORKER*1000)
        response = await stub.CreateProcessInstanceWithResult(cpiwrr)       # Start the worker and wait for the result!
        logging.info(f"Worker call end.   Loggid = {logg_id:>10}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, worker_name)

    res = json.loads(response.variables)
    # if 'DIGIT_ERROR' in res:
    #     res['_DIGIT_ERROR'] = res['DIGIT_ERROR']    # Temporary patch for old error-convention
    if '_DIGIT_ERROR' in res:
        status_code = int(res.get('_DIGIT_ERROR_CODE'),"400")
        return sanic.text(res['_DIGIT_ERROR'], status=status_code)  # Bad request

    for k in params:
        res.pop(k,None)              # Delete passed on params from response

    return sanic.json(res)


""" 
Workflow API
This is a POST which starts a workflow in Camunda.
A reference to the started workflow is returned in JSON format.
"""
@app.route("/workflow/<workflow_name:str>", methods=['POST'])
# @protected      # API requires a valid JWT token
async def start_workflow(request, workflow_name:str):
    stub = request.app.ctx.stub

    params = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
    params['_HTTP_METHOD'] = request.method  # Pass request method
    if request.json:
        params['_JSON_BODY'] = json.dumps(request.json)     # Add JSON-body if it exists
    userid = params.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Workflow start.   Loggid={logg_id};  Process={workflow_name};  userID={userid}")
        cpir = CreateProcessInstanceRequest(bpmnProcessId=workflow_name, version=-1, variables=json.dumps(params))
        response = await stub.CreateProcessInstance(cpir)
        logging.info(f"Workflow started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, workflow_name)

    return sanic.json({'processID':response.processInstanceKey})
    

"""
Filer API
This API is used for handling file uploading from apps.
All files are stored outside Camunda, in a separate storage.
A reference to the uploaded file is returned to the app, that can be used to pass on to a worker and workflow
Methods for retrieval and deletion of uploaded files are also available.
"""
@app.route("/filer/<file_id:strorempty>", methods=['POST', 'GET', 'DELETE'])
# @protected      # Requires a valid JWT token
async def handle_files(request, file_id:str):
    # multipart/form-data
    if request.method == 'POST':
        if len(request.files) != 1:
            return sanic.text("Missing file or more than one file!", status=400)  # Bad request
        fid = request.files.get(list(request.files)[0])     # Get the only file that is there
        if not fid:
            return sanic.text("Missing file data!", status=400)  # Bad request
        file_name_type = fid.name.split('.')[-1]
        file_type = fid.type.split('/')[-1]
        if len(fid.body) > 16000000:
            return sanic.text("File cannot be larger than 16 MB!", status=400)  # Bad request
        try:
            mongo = AsyncIOMotorClient(f"mongodb://root:{MONGO_ROOT_PWD}@{MONGO_HOST}")
            file_collection = mongo.BlobStorage.Files
            record = {'name': fid.name, 'type': fid.type, 'size': len(fid.body),
                      'created': int(time.time()), 'accessed': int(time.time()),
                      'status': "uploaded", 'data': fid.body}
            res = await file_collection.insert_one(record)
            object_id = str(res.inserted_id)
            logging.info(f"Uploaded file.    Name={fid.name};  Size={len(fid.body)};  Object ID={object_id}")

        except Exception as e:
            return sanic.text(f"MongoDB call returned {str(e)}", status=503)  # Bad request
    else:
        return sanic.text(f"{request.method} method is not yet implemented!", status=501)  # Not Yet Implemented

    return sanic.json({'id': object_id})


""" 
Epi forms API
Special API that is "forms aware". Always a POST that starts a process in Camunda.
A reference to the started process is returned in JSON format.
"""
# @app.route("/form/<form_process:str>", methods=['POST'])
# # @protected      # Requires a valid JWT token
# async def handle_form(request, form_process:str):
#     stub = request.app.ctx.stub
#     logg_id = str(uuid.uuid4().time_low)    # Just for logging

#     if request.content_type == "application/json":
#         logging.debug(f"Post JSON form with keys={list(request.json)}")
#         params = {k:{"value":v} for k,v in request.json.items()}        # POST has a json body with key/value pairs and with only string values
#     if request.content_type == "application/x-www-form-urlencoded":
#         logging.debug(f"Post URLencoded form with keys={list(request.form)}")
#         params = {k:{"value":v[0]} for k,v in request.form.items()}        # POST has a form body with key/value pairs and with only string values

#     userid = params.get('userid',"")    # It won't be here. Need to grab it from the form instead

#     try:
#         logging.info(f"Process start.   Loggid={logg_id};  Process={form_process};  userID={userid}")
#         cpir = CreateProcessInstanceRequest(bpmnProcessId=form_process, version=-1, variables=json.dumps(params))
#         response = await stub.CreateProcessInstance(cpir)
#         logging.info(f"Process started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
#     except grpc.aio.AioRpcError as grpc_error:
#         return handle_grpc_errors(grpc_error, form_process)

#     return sanic.text("HANDLED")


"""
LifeCheck API
Used by UI-apps to detect if Camunda is alife
"""

@app.route("/lifecheck", methods=['GET'])
async def handler(request):
    logging.debug("/lifecheck called")
    stub = request.app.ctx.stub
    try:
        topology = await stub.Topology(TopologyRequest())
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error)
    return sanic.json(["( ͡❛ ͜ʖ ͡❛)"])     # All OK!


"""
System test API
"""
# Returns the process environment variables. Can be used to check pod liveliness
@app.route("/environment", methods=['GET'])
async def handler(request):
    logging.debug("/environment called")
    e = [f"{k} = {v}" for k,v in os.environ.items()]
    e.append(f"CPU_CORES = {str(multiprocessing.cpu_count())}")
    e.append("ROUTES = "+", ".join([app.router.routes_all[x].path for x in app.router.routes_all]))
    return sanic.text("\n".join(e)+"\n")


# API that returns the Camunda version.
@app.route("/zeebe-engine", methods=['GET'])
async def handler(request):
    logging.debug("/zeebe-engine called")
    stub = request.app.ctx.stub
    try:
        topology = await stub.Topology(TopologyRequest())
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error)

    t = []
    t.append(f"Gateway version = {topology.gatewayVersion}")
    t.append(f"Cluster size = {topology.clusterSize}")
    t.append(f"Partitions count = {topology.partitionsCount}")
    t.append(f"Replication factor = {topology.replicationFactor}")
    return sanic.text("\n".join(t)+"\n")


""" 
Old process API
Will be removed when v1.0.0 is released!
"""
# @app.route("/process/<process_name:str>", methods=['GET', 'POST'])
# @protected      # API requires a valid JWT token
# async def start_process(request, process_name: str):
#     if request.method == "GET":
#         if process_name == "fetchFastighetInfo":
#              process_name = "propertyinfo"       # New worker name
#         return await start_worker(request,process_name)  # This is now a worker call
#     if request.method == "POST":
#         return await start_workflow(request,process_name)  # This is now a workflow call


"""
gRPC error handling functiom
"""
def handle_grpc_errors(grpc_error,process_name=""):
    if grpc_error.code() == grpc.StatusCode.NOT_FOUND:# Process not found
        loggtext = f"Camunda process {process_name} not found"
        logging.error(loggtext)
        return sanic.text(loggtext, status=404)  
    if grpc_error.code() == grpc.StatusCode.DEADLINE_EXCEEDED:  # Worker timeout
        loggtext = f"Camunda worker {process_name} timeout"
        logging.error(loggtext)
        return sanic.text(loggtext, status=408)
    if grpc_error.code() == grpc.StatusCode.UNAVAILABLE:  # Zeebe not respodning
        loggtext = f"Camunda/Zebee @{ZEEBE_ADDRESS} not responding!"
        logging.fatal(loggtext)
        return sanic.text(loggtext, status=503)
    loggtext = f"Unknown Camunda error: {grpc_error.code()}"
    logging.fatal(loggtext)
    return sanic.text(loggtext, status=500)  # Unhandled error


"""
Test and develop API's
"""
# # Protected function
# @app.route("/protected", methods=['GET'])
# # @protected
# async def handler(request):
#     return sanic.text("Hello World!")

# # Create JWT token
# import jwt
# from datetime import datetime, timedelta, timezone
# @app.route("/token", methods=['GET'])
# async def handler(request):
#     token = "NO KEY AVAILABLE TO GENERATE TOKEN!"
#     if request.app.ctx.jwt_secret is not None:
#         exp = {"exp": datetime.now(tz=timezone.utc)+timedelta(days=30)}
#         token = jwt.encode(exp, request.app.ctx.jwt_secret, algorithm="HS256")
#     return sanic.text(token)


"""
MAIN function (starting point)
"""
def main():
    # Enable logging. INFO is default
    logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO, format=LOGFORMAT)     # Default logging level

    # if JWT_SECRET is None and not DISABLE_AUTH:
    #     logging.fatal(f"Missing JWT_SECRET in environment")
    #     return      # This will kill the process

    # if DISABLE_AUTH:
    #     logging.info("API authentication is disabled!")
    # if DISABLE_TASK_API:
    #     logging.info("Task API is disabled!")


    app.run(host="0.0.0.0", port=8000, access_log=DEBUG_MODE, motd=DEBUG_MODE, dev=DEV_MODE)      # Run a single worker on port 8000


if __name__ == '__main__':
    main()
