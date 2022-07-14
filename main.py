# camunda-python-wrapper
#
# This is a convenience API that wraps Camunda process API
# It implements a GET and a POST method where the GET method waits for Camunda to get to a manual task, where the result is picked up and returned
# 

import os
import multiprocessing
import uuid
import time
import logging

import sanic
import json

import grpc
from zeebe_grpc import gateway_pb2_grpc
from zeebe_grpc.gateway_pb2 import (
    CreateProcessInstanceRequest,
    CreateProcessInstanceWithResultRequest,
    TopologyRequest
)

""" 
Environment
"""

ZEEBE_ADDRESS = os.getenv('ZEEBE_ADDRESS',"localhost:26500")
DEBUG_MODE = os.getenv('DEBUG','false') == "true"
DEV_MODE = os.getenv('DEV_MODE','false') == "true"

MAX_TIME = 60 # Max time in seconds to wait for a GET to return result
LOGFORMAT = "%(asctime)s %(funcName)-10s [%(levelname)s] %(message)s"


""" 
Sanic app instance
"""

app = sanic.Sanic("Camunda_Wrapper")       # A Sanic instance

""" 
startup and shutdown functions
"""

@app.before_server_start
def startup(app, loop):
    logging.info("Starting Camunda Wrapper")
    app.ctx.channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
    app.ctx.stub = gateway_pb2_grpc.GatewayStub(app.ctx.channel)

@app.after_server_stop
def shutdown(app, loop):
    logging.info("Stopping Camunda Wrapper")
    app.ctx.channel.close()   # RuntimeWarning: coroutine 'Channel.close' was never awaited ????


""" 
Integration API
"""

@app.route("/integration/<process_name:str>", methods=['GET'])
async def start_integration(request, process_name: str):
    stub = request.app.ctx.stub
    query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args

    userid = query_args.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Integration call start. Loggid={logg_id:>10}  Integration={process_name}  userID={userid}")
        response = await stub.CreateProcessInstanceWithResult(
            CreateProcessInstanceWithResultRequest(
                request=CreateProcessInstanceRequest(bpmnProcessId=process_name, version=-1, variables=json.dumps(query_args)),
                requestTimeout=MAX_TIME*1000))
        logging.info(f"Integration call end.   Loggid={logg_id:>10}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, process_name)

    res = json.loads(response.variables)
    for k in query_args:
        res.pop(k,None)              # Delete query_args if still around (Should be done in the worker?)

    return sanic.response.json(res)

""" 
Process API
"""

@app.route("/process/<process_name:str>", methods=['GET', 'POST'])
async def start_process(request, process_name: str):
    if request.method == "GET":
        return await start_integration(request,process_name)  # This is actually an integration?

    stub = request.app.ctx.stub

    query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
    json_body = {'JSON_BODY':json.dumps(request.json)}         # And the JSON body
    local_args = {'HTTP_METHOD':request.method, 'PROCESS_NAME':process_name}  # Pass request method and called process
    params = query_args | json_body | local_args

    userid = query_args.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Process start.   Loggid={logg_id}  Process={process_name}  userID={userid}")
        response = await stub.CreateProcessInstance(
            CreateProcessInstanceRequest(bpmnProcessId=process_name, version=-1, variables=json.dumps(params)))
        logging.info(f"Process started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, process_name)

    return sanic.response.json({'processID':response.processInstanceKey})
    

""" 
Epi forms API
"""

@app.route("/form/process/<process_name:str>", methods=['POST'])
async def handler(request, process_name: str):
    logging.debug(f"Form post to process={process_name}")

    stub = request.app.ctx.stub

    if request.content_type == "application/json":
        logging.debug(f"Post JSON form with keys={list(request.json)}")
        params = {k:{"value":v} for k,v in request.json.items()}        # POST has a json body with key/value pairs and with only string values
    if request.content_type == "application/x-www-form-urlencoded":
        logging.debug(f"Post URLencoded form with keys={list(request.form)}")
        params = {k:{"value":v[0]} for k,v in request.form.items()}        # POST has a form body with key/value pairs and with only string values

    userid = params.get('userid',"")    # It won't be here. Need to grab it from the form instead
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Process start.   Loggid={logg_id}  Process={process_name}  userID={userid}")
        response = await stub.CreateProcessInstance(
            CreateProcessInstanceRequest(bpmnProcessId=process_name, version=-1, variables=json.dumps(params)))
        logging.info(f"Process started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, process_name)

    return sanic.response.text("POSTED")


"""
Task API
"""

# @app.route("/tasks/<task_name:str>", methods=['GET', 'POST', 'PUT'])
# async def handler(request, task_name: str):
#     query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
#     async with httpx.AsyncClient() as client:
#         payload = {"name":task_name}
#         # payload = {"name":"SIGN Document"}
#         r = await client.get(f"{CAMUNDA}/task",params=payload)
        
#     # return text("OK")
#     return json(r.json())


"""
System test API
"""

# Returns the process environment variiables. Can be used to check liveliness
@app.route("/environment", methods=['GET'])
async def handler(request):
    logging.debug("/environment called")
    e = [f"{k} = {v}" for k,v in os.environ.items()]
    e.append(f"CPU_CORES = {str(multiprocessing.cpu_count())}")
    e.append("ROUTES = "+", ".join([app.router.routes_all[x].path for x in app.router.routes_all]))
    return sanic.response.text("\n".join(e)+"\n")


# API that returns the Camunda version.  Can be used to check Camunda liveliness
@app.route("/zeebe-engine", methods=['GET'])
async def handler(request):
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
    return sanic.response.text("\n".join(t)+"\n")


"""
gRPC error handling functiom
"""

def handle_grpc_errors(grpc_error,process_name=""):
    if grpc_error.code() == grpc.StatusCode.NOT_FOUND:# Process not found
        loggtext = f"Camunda process {process_name} not found"
        logging.error(loggtext)
        return sanic.response.text(loggtext, status=404)  
    if grpc_error.code() == grpc.StatusCode.DEADLINE_EXCEEDED:  # Process timeout
        loggtext = f"Camunda process {process_name} timeout"
        logging.error(loggtext)
        return sanic.response.text(loggtext, status=504)
    if grpc_error.code() == grpc.StatusCode.UNAVAILABLE:  # Zeebe not respodning
        loggtext = f"Camunda/Zebee @{ZEEBE_ADDRESS} not responding!"
        logging.fatal(loggtext)
        return sanic.response.text(loggtext, status=503)
    loggtext = f"Unknown Camunda error: {grpc_error.code()}"
    logging.fatal(loggtext)
    return sanic.response.text(loggtext, status=500)  # Unhandled error


"""
Beta API's
"""


"""
Test and develop API's
"""


"""
MAIN function (starting point)
"""

if __name__ == '__main__':
    # Enable logging. INFO is default
    logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO, format=LOGFORMAT)     # Default logging level

    app.run(host="0.0.0.0", port=8000, access_log=DEBUG_MODE, dev=DEV_MODE)      # Run a single worker on port 8000
