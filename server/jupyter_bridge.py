
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
import time
import logging
from logging.handlers import RotatingFileHandler


app = Flask(__name__)

JUPYTER_BRIDGE_VERSION = '0.0.2'


# Set up detail logger
logger = logging.getLogger('jupyter-bridge')
logger_handler = RotatingFileHandler('jupyter-bridge.log', maxBytes=1048576, backupCount=10, encoding='utf8')
logger_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logger.setLevel('DEBUG')
logger.addHandler(logger_handler)

PAD_MESSAGE = True # For troubleshooting truncated FIN terminator that loses headers and data
DEQUEUE_TIMEOUT_SECS = 15 # Something less that connection timeout, but long enough not to cause caller to create a dequeue blizzard
DEQUEUE_POLLING_SECS = 0.1 # A fast polling rate means overall fast response to clients

# Redis message format:
MESSAGE = b'message'
POSTED_TIME = b'posted_time'
PICKUP_WAIT = b'pickup_wait'
PICKUP_TIME = b'pickup_time'

# Redis key constants
REPLY = 'reply'
REQUEST = 'request'

# Start the Redis client ... assume that the server has already started
logger.debug('starting Jupyter-bridge with python environment: \n' + '\n'.join(sys.path))
try:
    import redis
    redis_db = redis.Redis('localhost')
    logger.debug('started redis connection')
except Exception as e:
    logger.debug(f'exception starting redis: {e!r}')

@app.route('/ping', methods=['GET'])
def ping():
    logger.debug('into ping')
    try:
        return Response(f'pong {JUPYTER_BRIDGE_VERSION}', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of ping')

@app.route('/queue_request', methods=['POST'])
def queue_request():
    logger.debug('into queue_request')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']

            # Send new request
            if request.content_type.startswith('application/json'):
                message = request.get_data()

                # Verify that the reply to a previous request was picked up before issuing new request
                reply_key = f'{channel}:{REPLY}'
                last_reply = redis_db.hget(reply_key, MESSAGE)
                if last_reply:
                    raise Exception(f'Reply not picked up before new request. Reply: {last_reply}, Request: {message}')

                _enqueue(REQUEST, channel, message)
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be application/json')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"queue_request exception {e!r}")
        return Response(_exception_message(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of queue_request')

@app.route('/queue_reply', methods=['POST'])
def queue_reply():
    logger.debug('into queue_reply')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            if request.content_type.startswith('text/plain'):
                message = request.get_data()
                _enqueue(REPLY, channel, message)
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be text/plain')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"queue_reply exception {e!r}")
        return Response(_exception_message(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of queue_reply')

@app.route('/dequeue_request', methods=['GET'])
def dequeue_request():
    logger.debug('into dequeue_request')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue(REQUEST, channel, 'reset' in request.args) # Will block waiting for message
            if message is None:
                return Response('', status=408, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                message = _add_padding(message)
                return Response(message, status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"dequeue_request exception {e!r}")
        return Response(_exception_message(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of dequeue_request')

@app.route('/dequeue_reply', methods=['GET'])
def dequeue_reply():
    logger.debug('into dequeue_reply')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue(REPLY, channel, 'reset' in request.args) # Will block waiting for message
            if message is None:
                return Response('', status=408, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                message = _add_padding(message)
                return Response(message, status=200, content_type='application/json',
                                headers={'Access-Control-Allow-Origin': '*'})
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"dequeue_reply exception {e!r}")
        return Response(_exception_message(e), status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of dequeue_reply')

def _enqueue(operation, channel, msg):
    logger.debug(f' into _enqueue: {operation}, channel: {channel}, msg: {msg}')

    try:
        key = f'{channel}:{operation}'
        cur_value = redis_db.hgetall(key)
        if len(cur_value) == 0 or not MESSAGE in cur_value:
            _hmset_test(key, {MESSAGE: msg, PICKUP_TIME: '', PICKUP_WAIT: '', POSTED_TIME: time.asctime()})
            _expire(key)
        else:
            raise Exception(f'Channel {key} contains unprocessed message')
    finally:
        logger.debug(' out of _enqueue')

def _dequeue(operation, channel, reset_first):
    logger.debug(f' into _dequeue: {operation}, channel: {channel}, reset_first: {reset_first}')
    message = None
    try:
        key = f'{channel}:{operation}'
        if reset_first: # Clear out any (presumably dead) reader ... assume first dequeue precedes first enqueue
            _del_message(key)
        _hmset_test(key, {PICKUP_WAIT: time.asctime(), PICKUP_TIME: ''})

        message = redis_db.hget(key, MESSAGE)
        dequeue_timeout_secs_left = DEQUEUE_TIMEOUT_SECS
        while message is None and dequeue_timeout_secs_left > 0:
            time.sleep(DEQUEUE_POLLING_SECS)
            dequeue_timeout_secs_left -= DEQUEUE_POLLING_SECS
            message = redis_db.hget(key, MESSAGE)
        # TODO: Polling is good enough for now, but for scaling, replace with await

        if message:
            _del_message(key)
            _hmset_test(key, {PICKUP_TIME: time.asctime()})
        else:
            logger.debug(f'  _dequeue timed out: {operation}, channel: {channel}')
    finally:
        logger.debug(' out of _dequeue')

    return message

def _add_padding(message):
    if PAD_MESSAGE:
        if isinstance(message, str):
            message += ' ' * 1500
        elif isinstance(message, bytes):
            message += (' ' * 1500).encode('ascii')
    return message

def _exception_message(e):
    try:
        return e.response.text if e.response and e.response.text else ''
    except:
        return str(e)

def _hmset_test(key, value):
    if not redis_db.hmset(key, value):
        raise Exception(f'redis failed setting {key} to {value}')

def _del_message(key):
    if redis_db.hdel(key, MESSAGE) != 1:
        raise Exception(f'redis failed deleting {key} subkey {MESSAGE}')

def _expire(key):
    if redis_db.expire(60 * 60 * 24) != 1:
        raise Exception(f'redis failed expiring {key}')

if __name__=='__main__':
    debug = False
    if len(sys.argv) > 1:
        host_ip = sys.argv[1]
        debug = True
    else:
        host_ip = '0.0.0.0'
    app.run(debug=debug, host=host_ip)
