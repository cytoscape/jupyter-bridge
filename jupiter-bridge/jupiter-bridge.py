
"""Jupyter-bridge is a Flask service that executes on a server accessible to both a remote Jupyter server and browser-based
Jupyter client. Code running on the server calls Jupyter-bridge to queue a request that the client will execute, and the
client will use Jupyter-bridge to return a reply. This enables the client to execute an HTTP request on a client-based
application such as Cytoscape, and then return the Cytoscape result. This is almost possible via the Jupyter server's
%%javascript magic combined with the client's IPython.notebook.kernel.execute() function, except that the server
won't see the reply until all cells are executed -- too late.

A channel is identified as a UUID that both the client and server share before trying to use this bridge. Initially,
the client waits on a request on that channel, and the server eventually sends it. The client then executes the HTTP
operation identifies in the request. The server waits for a reply on that channel, and the client eventually sends it.
The request and reply operations are symmetrical, and so share common code. However, the request operation saves
the request in a request map (keyed by channel ID), and the reply operation saves the reply in a reply map.

Queuing requests is not allowed. If the server sends a request before the client operates on it, an error occurs.
Likewise, when the client sends a reply, it assumes the server will receive it before the client needs to send a
subsequent reply.

Python maps are not thread-safe, so the request and reply maps are protected by semaphore. A message is stored in
a Queue of length 1 so that the message receiver can block while waiting for it.

Violation of an integrity assertion implies either a calling error at either the Jupyter server or Jupyter client. If
no violation occurs, a Jupyter-bridge call will return OK (for send operations) or OK and payload (for receive
operations). If an error occurs, an HTTP 500 will be returned.

Requests are assumed to be a JSON structure that describes the Cytoscape HTTP call. Replies are assumed to be the
raw text returned by Cytoscape, and may include JSON that will be recovered by the requestor when it receives the
reply.

"""
from flask import Flask, request, Response
import sys
import json
import threading
import queue

app = Flask(__name__)

request_map = dict()
request_map_lock = threading.Lock()

reply_map = dict()
reply_map_lock = threading.Lock()


@app.route('/queue_request', methods=['PUT'])
def queue_request():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            if request.content_type.startswith('application/json'):
                data = request.get_data()
                message = json.loads(data.decode('utf-8'))
                _enqueue(request_map, request_map_lock, channel, message)
                return Response('', status=200, mimetype='text/plain')
            else:
                raise Exception('Payload must be application/json')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, mimetype='text/plain')

@app.route('/queue_reply', methods=['PUT'])
def queue_reply():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            if request.content_type.startswith('text/plain'):
                message = request.get_data()
                _enqueue(reply_map, reply_map_lock, channel, message)
                return Response('', status=200, mimetype='text/plain')
            else:
                raise Exception('Payload must be text/plain')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, mimetype='text/plain')

@app.route('/dequeue_request', methods=['GET'])
def dequeue_request():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue(request_map, request_map_lock, channel) # Will block waiting for message
            message = json.dumps(message)
            return Response(message, status=200, mimetype='application/json')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, mimetype='text/plain')


@app.route('/dequeue_reply', methods=['GET'])
def dequeue_reply():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue(reply_map, reply_map_lock, channel) # Will block waiting for message
            return Response(message, status=200, mimetype='text/plain')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, mimetype='text/plain')

def _enqueue(map, lock, channel, msg):
    lock.acquire()
    try:
        if channel in map:
            q = map[channel]
            if q.full(): raise Exception(f'Channel {channel} contains unprocessed message')
        else:
            q = queue.Queue(1)
        q.put(msg)
        map[channel] = q
    finally:
        lock.release()

def _dequeue(map, lock, channel):
    lock.acquire()
    try:
        if channel in map:
            q = map[channel]
        else:
            q = queue.Queue(1)
            map[channel] = q
    finally:
        lock.release()
    return q.get() # Block if no message, and return message and queue empty



if __name__=='__main__':
    if len(sys.argv) > 2:
        host_ip = sys.argv[1]
    else:
        host_ip = '127.0.0.1'
    if len(sys.argv) > 3:
        port = sys.argv[2]
    else:
        port = 9529
    app.run(debug=True, host=host_ip, port=port)
