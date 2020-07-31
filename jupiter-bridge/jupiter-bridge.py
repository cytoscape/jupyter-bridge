
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
import time
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)


# Set up detail logger
logger = logging.getLogger('jupyter-bridge')
logger_handler = RotatingFileHandler('jupyter-bridge.log', maxBytes=1048576, backupCount=10, encoding='utf8')
logger_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logger.setLevel('DEBUG')
logger.addHandler(logger_handler)

# Set up bridge data structures
channel_status_lock = threading.Lock()
channel_status = dict()
"""Structure:
    request: {q: Queue, lock: lock, status: {message: text, posted_time: time, pickup_wait: time, pickup_time: time}}
    reply:   {q: Queue, lock: lock, status: {message: text, posted_time: time, pickup_wait: time, pickup_time: time}}
"""
empty_status = {'message': None, 'posted_time': None, 'pickup_wait': None, 'pickup_time': None}
debug_option = 'dbg_none'

PAD_MESSAGE = True # For troubleshooting truncated FIN terminator that loses headers and data


@app.route('/queue_request', methods=['POST'])
def queue_request():
    logger.debug('into queue_request')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']

            # Send new request
            if request.content_type.startswith('application/json'):
                data = request.get_data()
                message = json.loads(data.decode('utf-8'))

                # Verify that any previous reply has been picked up before trying to send new request
                # reply_status = channel_status[channel]['reply']['status']
                #
                #
                # if not reply_status['posted_time'] is None and reply_status['pickup_time'] is None:
                #     raise Exception(f'Reply not picked up before new request, reply: ' + str(reply_status['message']) + ', request: ' + str(message))
                # channel_status[channel]['reply']['status'] = empty_status.copy()

                logger.debug('calling _enqueue')
                _enqueue('request', channel, message)
                logger.debug('calling _enqueue')
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be application/json')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug('Exception: ' + str(e))
        return Response(str(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('leaving queue_request')

"""
@app.route('/queue_reply', methods=['POST'])
def queue_reply():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            if request.content_type.startswith('text/plain'):
                message = request.get_data()
                _enqueue('reply', channel, message)
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be text/plain')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})

@app.route('/dequeue_request', methods=['GET'])
def dequeue_request():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue('request', channel, 'reset' in request.args) # Will block waiting for message
            message = json.dumps(message)
            if PAD_MESSAGE: message += ' '*1500
            return Response(message, status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
"""

@app.route('/dequeue_reply', methods=['GET'])
def dequeue_reply():
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue('reply', channel, 'reset' in request.args) # Will block waiting for message
            # Setting content_type because using mime_type would add a charset, which we want
            # to defer to ultimate client.
            # Setting application/json to avoid ultimate client assuming charset is 'ISO-8859-1'
            # We want charset to be whatever is local to the client.
            # TODO: This should probably be passed up from the javascript layer that got it from
            # cyREST.
            if PAD_MESSAGE:
                if isinstance(message, str): message += ' '*1500
                elif isinstance(message, bytes): message += (' '*1500).encode('ascii')
            return Response(message, status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        return Response(str(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})

@app.route('/status', methods=['GET'])
def status():

    def return_msg(msg):
        try:
            json.dumps(msg) # See if message is real JSON ... if so, leave it be
        except:
            msg = str(msg) # Not JSON, so return a string type
        return msg

    try:
        channel_status_lock.acquire()
        result = {} # Return the serializable fields, and best effort for message value
        for channel, channel_rec in channel_status.items():
            request_status = channel_rec['request']['status']
            request_status['message'] = return_msg(request_status['message'])
            reply_status = channel_rec['reply']['status']
            reply_status['message'] = return_msg(reply_status['message'])
            result[channel] = {'request': request_status, 'reply': reply_status}
        return Response(json.dumps(result), status=200, mimetype='application/json', headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return Response(str(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        channel_status_lock.release()


def _enqueue(operation, channel, msg):
    post, post_status = _verify_channel(channel, operation)
    if debug_option == 'dbg_msg':
        print(f' enqueue: {operation}, channel: {channel}, msg: {msg}')
    try:
        post['lock'].acquire()
        if not post['q'].empty():
            raise Exception(f'Channel {channel} contains unprocessed message')
        if not post_status['pickup_time'] is None:
            # Prior message was picked up, so get rid of waiter status
            post_status['pickup_wait'] = post_status['pickup_time'] = None
        post_status['posted_time'] = time.asctime()
        post_status['message'] = msg
        post['q'].put(msg)
    finally:
        post['lock'].release()

def _dequeue(operation, channel, reset_first):
    pickup, pickup_status = _verify_channel(channel, operation)
    try:
        pickup['lock'].acquire()
        if reset_first: # Clear out any (presumably dead) reader
            pickup['q'].put('dying breath') # Satisfy outstanding (dead?) reader
            pickup['q'] = queue.Queue(1) # Make double-sure queue is clean
        pickup_status['pickup_wait'] = time.asctime()
        pickup_status['pickup_time'] = None
        if pickup['q'].empty(): # clear out already-read message
            pickup_status['message'] = None
            pickup_status['posted_time'] = None
    finally:
        pickup['lock'].release()

    msg = pickup['q'].get() # Block if no message, and return message and queue empty
    if debug_option == 'dbg_msg':
        print(f' dequeue: {operation}, channel: {channel}, msg: {msg}')

    try:
        pickup['lock'].acquire()
        # Don't erase pickup_wait here because it can be useful to see how long a response took
        pickup_status['pickup_time'] = time.asctime()
    finally:
        pickup['lock'].release()

    return msg

def _verify_channel(channel, operation):
    try:
        channel_status_lock.acquire()
        if not channel in channel_status:
            channel_status[channel] = {'request': {'q': queue.Queue(1), 'lock': threading.Lock(), 'status': empty_status.copy()},
                                       'reply'  : {'q': queue.Queue(1), 'lock': threading.Lock(), 'status': empty_status.copy()}}
    finally:
        channel_status_lock.release()

    return channel_status[channel][operation], \
           channel_status[channel][operation]['status']

if __name__=='__main__':
    app.run(host='0.0.0.0')
    # if len(sys.argv) > 1:
    #     host_ip = sys.argv[1]
    # else:
    #     host_ip = '127.0.0.1'
    # if len(sys.argv) > 2:
    #     port = sys.argv[2]
    # else:
    #     port = 9529
    # if len(sys.argv) > 3:
    #     debug_option = sys.argv[3]
    # app.run(debug=True, host=host_ip, port=port)
