# camunda-python-wrapper
#
# This is a convenience API that wraps Camunda process API
# It implements a GET and a POST method where the GET method waits for Camunda to get to a manual task, where the result is picked up and returned
# 

import os
import multiprocessing
import uuid
import logging
import asyncio

import sanic
import json

import grpc
from zeebe_grpc import gateway_pb2_grpc
from zeebe_grpc.gateway_pb2 import (
    CreateProcessInstanceRequest,
    CreateProcessInstanceWithResultRequest,
    ActivateJobsRequest,
    CompleteJobRequest,
    TopologyRequest)

from auth import protected


""" 
Environment
"""
ZEEBE_ADDRESS = os.getenv('ZEEBE_ADDRESS',"camunda8-zeebe-gateway:26500")   # Zeebe adress and port
DEBUG_MODE = os.getenv('DEBUG','false') == "true"                           # Enable global DEBUG logging
DEV_MODE = os.getenv('DEV_MODE','false') == "true"                          # Sanic develpoment mode

JWT_SECRET = os.getenv('JWT_SECRET',None)                                   # Secret (!!!) for JWT generation and verification
DISABLE_AUTH = os.getenv('DISABLE_AUTH','false') == "true"                  # Disable API authentication for testing purposes
DISABLE_TASK_API = os.getenv('DISABLE_TASK_API','false') == "true"          # Disable wrapper task API for testing purposes

MAX_TIME = 60                                                               # Max time in seconds to wait for a GET to return result
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
    app.ctx.jwt_secret = JWT_SECRET
    app.ctx.disable_auth = DISABLE_AUTH
    app.ctx.running = True
    app.ctx.channel = grpc.aio.insecure_channel(ZEEBE_ADDRESS)
    app.ctx.stub = gateway_pb2_grpc.GatewayStub(app.ctx.channel)
    if not DISABLE_TASK_API:
        app.ctx.collect_task = asyncio.create_task(collect_task(app.ctx))    # Start collect task

@app.after_server_stop
def shutdown(app, loop):
    logging.info("Stopping Camunda Wrapper")
    app.ctx.running = False
    # app.ctx.channel.close()   # Can't do close() here! Can be skipped?


""" 
Worker API
This is a GET which calls a Camunda worker and returns the result from that worker.
All results are in JSON format.
Testing with PATCH method as well
"""
@app.route("/worker/<worker_name:str>", methods=['GET', 'PATCH'])
@protected      # API requires a valid JWT token
async def start_worker(request, worker_name: str):
    stub = request.app.ctx.stub

    query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
    query_args['HTTP_METHOD'] = request.method  # Pass request method
    userid = query_args.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Worker call start. Loggid = {logg_id:>10};  Integration = {worker_name};  userID = {userid}")
        response = await stub.CreateProcessInstanceWithResult(
            CreateProcessInstanceWithResultRequest(
                request=CreateProcessInstanceRequest(bpmnProcessId=worker_name, version=-1, variables=json.dumps(query_args)),
                requestTimeout=MAX_TIME*1000))
        logging.info(f"Worker call end.   Loggid = {logg_id:>10}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, worker_name)

    res = json.loads(response.variables)
    # for k in query_args:
    #     res.pop(k,None)              # Delete query_args if still around (Should be done in the worker?)
    # if 'RESOBJ' in res:             # Return values are a complete json object (should be in DB?)
    #     res = json.loads(res['RESOBJ']['value'])

    return sanic.json(res)


""" 
Workflow API
This is a POST which starts a workflow in Camunda.
A reference to the started workflow is returned in JSON format.
"""
@app.route("/workflow/<workflow_name:str>", methods=['POST'])
@protected      # API requires a valid JWT token
async def start_workflow(request, workflow_name: str):
    stub = request.app.ctx.stub

    query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
    json_body = {'JSON_BODY':json.dumps(request.json)}         # And the JSON body
    local_args = {'HTTP_METHOD':request.method, 'workflow_name':workflow_name}  # Pass request method and called process
    params = query_args | json_body | local_args
    userid = query_args.get('userid',"")    # Just for logging
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    try:
        logging.info(f"Workflow start.   Loggid={logg_id};  Process={workflow_name};  userID={userid}")
        response = await stub.CreateProcessInstance(
            CreateProcessInstanceRequest(bpmnProcessId=workflow_name, version=-1, variables=json.dumps(params)))
        logging.info(f"Workflow started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, workflow_name)

    return sanic.json({'processID':response.processInstanceKey})
    

""" 
Epi forms API
Special API tht is "forms aware". Always a POST that starts a process in Camunda.
A reference to the started process is returned in JSON format.
"""
@app.route("/form/<form_process:str>", methods=['POST'])
@protected      # Requires a valid JWT token
async def handle_form(request, form_process: str):
    stub = request.app.ctx.stub
    userid = params.get('userid',"")    # It won't be here. Need to grab it from the form instead
    logg_id = str(uuid.uuid4().time_low)    # Just for logging

    if request.content_type == "application/json":
        logging.debug(f"Post JSON form with keys={list(request.json)}")
        params = {k:{"value":v} for k,v in request.json.items()}        # POST has a json body with key/value pairs and with only string values
    if request.content_type == "application/x-www-form-urlencoded":
        logging.debug(f"Post URLencoded form with keys={list(request.form)}")
        params = {k:{"value":v[0]} for k,v in request.form.items()}        # POST has a form body with key/value pairs and with only string values

    try:
        logging.info(f"Process start.   Loggid={logg_id};  Process={form_process};  userID={userid}")
        response = await stub.CreateProcessInstance(
            CreateProcessInstanceRequest(bpmnProcessId=form_process, version=-1, variables=json.dumps(params)))
        logging.info(f"Process started. Loggid={logg_id}  Version={response.version}  Instance={response.processInstanceKey}")
    except grpc.aio.AioRpcError as grpc_error:
        return handle_grpc_errors(grpc_error, form_process)

    return sanic.text("POSTED")


"""
Task API
"""
@app.route("/tasks/<jobKey:strorempty>", methods=['GET', 'POST'])
@protected      # Requires a valid JWT token
async def handler(request):
    # GET method returns current acrive user tasks
    # query args can be bpmnProcessId, elementId and/or assignedTo
    # No query args returns all user tasks
    if request.method == "GET":
        query_args = {q[0]:q[1] for q in request.get_query_args(keep_blank_values=True)}     # Grab all query_args
        res = request.app.ctx.active_tasks
        # TODO: Filter out tasks
        return sanic.json(res)

    # POST method completes the requested task with potential updated variables
    # await stub.CompleteJob(gateway_pb2.CompleteJobRequest(jobKey=job.key, variables=json.dumps(payload)))
    return sanic.text("OK")


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
    return sanic.text("\n".join(e)+"\n")


# API that returns the Camunda version.  Can be used to check Camunda liveliness
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
@app.route("/process/<process_name:str>", methods=['GET', 'POST'])
@protected      # API requires a valid JWT token
async def start_process(request, process_name: str):
    if request.method == "GET":
        return await start_worker(request,process_name)  # This is now a worker call
    if request.method == "POST":
        return await start_workflow(request,process_name)  # This is now a workflow call


"""
Asynchronous task that periodically collects active tasks from Camunda
"""
async def collect_task(ctx):
    logging.info("Collect Task started!")
    ctx.active_tasks = []
    topic = "io.camunda.zeebe:userTask"     # Worker topic for all BPMN user tasks in Zeebe
    locktime = 1                            # Don't know if this works?
    worker_id = str(uuid.uuid4().time_low)  # Random worker ID
    ajr = ActivateJobsRequest(type=topic,worker=worker_id,timeout=locktime,
                              maxJobsToActivate=10000,requestTimeout=-1)    # Get user tasks request
    while(ctx.running):
        async for response in ctx.stub.ActivateJobs(ajr):   # Get all active user tasks
            active_tasks = []
            logging.debug(f"Found {len(response.jobs)} active user tasks")
            for job in response.jobs:   # Loop through all returned user tasks
                task = {}
                task['key'] = job.key
                task['bpmnProcessId'] = job.bpmnProcessId
                task['elementId'] = job.elementId
                task['customHeaders'] = json.loads(job.customHeaders)
                task['variables'] = json.loads(job.variables)
                active_tasks.append(task)   # Append it to the active_tasks list

        ctx.active_tasks = active_tasks     # Save it for global use
        await asyncio.sleep(30)      # Collect tasks every 30 seconds

    logging.info("Collect Task stopped!")


"""
gRPC error handling functiom
"""
def handle_grpc_errors(grpc_error,process_name=""):
    if grpc_error.code() == grpc.StatusCode.NOT_FOUND:# Process not found
        loggtext = f"Camunda process {process_name} not found"
        logging.error(loggtext)
        return sanic.text(loggtext, status=404)  
    if grpc_error.code() == grpc.StatusCode.DEADLINE_EXCEEDED:  # Process timeout
        loggtext = f"Camunda process {process_name} timeout"
        logging.error(loggtext)
        return sanic.text(loggtext, status=504)
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
# Protected function
@app.route("/protected", methods=['GET'])
@protected
async def handler(request):
    return sanic.text("Hello World!")

# Create JWT token
import jwt
from datetime import datetime, timedelta, timezone
@app.route("/token", methods=['GET'])
async def handler(request):
    token = "NO KEY AVAILABLE TO GENERATE TOKEN!"
    if request.app.ctx.jwt_secret is not None:
        exp = {"exp": datetime.now(tz=timezone.utc)+timedelta(days=30)}
        token = jwt.encode(exp, request.app.ctx.jwt_secret, algorithm="HS256")
    return sanic.text(token)


"""
MAIN function (starting point)
"""
def main():
    # Enable logging. INFO is default
    logging.basicConfig(level=logging.DEBUG if DEBUG_MODE else logging.INFO, format=LOGFORMAT)     # Default logging level

    if JWT_SECRET is None and not DISABLE_AUTH:
        logging.fatal(f"Missing JWT_SECRET in environment")
        return      # This will kill the process

    if DISABLE_AUTH:
        logging.info("API authentication is disabled!")

    app.run(host="0.0.0.0", port=8000, access_log=DEBUG_MODE, motd=DEBUG_MODE, dev=DEV_MODE)      # Run a single worker on port 8000


if __name__ == '__main__':
    main()