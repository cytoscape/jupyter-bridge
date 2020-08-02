
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
    request: {q: Queue, qq:message, lock: lock, status: {message: text, posted_time: time, pickup_wait: time, pickup_time: time}}
    reply:   {q: Queue, qq:message, lock: lock, status: {message: text, posted_time: time, pickup_wait: time, pickup_time: time}}
"""
empty_status = {'message': None, 'posted_time': None, 'pickup_wait': None, 'pickup_time': None}

PAD_MESSAGE = True # For troubleshooting truncated FIN terminator that loses headers and data
DEQUEUE_TIMEOUT_SECS = 15 # Something less that connection timeout, but long enough not to cause caller to create a dequeue blizzard


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

                _enqueue('request', channel, message)
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be application/json')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"queue_request exception {e!r}")
        e_message = e.response.text if e.response and e.response.text else ''
        return Response(e_message, status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
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
                _enqueue('reply', channel, message)
                return Response('', status=200, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
            else:
                raise Exception('Payload must be text/plain')
        else:
            raise Exception('Channel is missing in parameter list')
    except Exception as e:
        logger.debug(f"queue_reply exception {e!r}")
        e_message = e.response.text if e.response and e.response.text else ''
        return Response(e_message, status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of queue_reply')

@app.route('/dequeue_request', methods=['GET'])
# There is a problem with dequeue_request. Suppose that a client executes this. It's
# waiting for something in the queue, and when a message shows up, it grabs the message, and
# the message is returned. That's the way it's supposed to work. Suppose, though, that a message
# doesn't appear for a long time and the client is waiting for a long time. The web server may
# kill the connection because of the timeout. This service keeps waiting, though, and when
# it finally gets a request, it returns it on an HTTP connection that no longer has a listener.
# It doesn't help that the client re-starts the service call because by then, the message has
# disappeared. A variant of this is that the client re-starts the service several times, which
# causes the next several messages to disappear because their connection go severed, too.
#
# There are a few ways around this.
# 1) Turn this service into a poll ... where the message is returned if there is one, and
#    an error is returned if there is no message. This would avoid the connection termination
#    problem, which is a problem no matter how long the server connection timeout is set. The
#    downside to this is that the client has to periodically re-poll, which adds traffic.
# 2) Re-queue the message immediately after it's de-queued, and then create another service
#    that kills the re-queued message. This adds complexity to this protocol, but it allows
#    the client to wait until the connection is killed before re-starting the service. Note
#    that a Queue is used to hold request messages, as if it's possible to have several
#    outstanding requests at the same time. This is misleading, as our protocol requires
#    that a requestor do nothing except post the request and await a reply.
# 3) A variant of #1 is to allow the poll to linger for a number of seconds before returning
#    an error. This cuts down on the re-polling traffic and improves responsiveness. This may be
#    best because it means that server resources won't be tied up forever if a client never
#    sends another message.
def dequeue_request():
    logger.debug('into dequeue_request')
    try:
        if 'channel' in request.args:
            channel = request.args['channel']
            message = _dequeue('request', channel, 'reset' in request.args) # Will block waiting for message
            message = json.dumps(message)
            if PAD_MESSAGE: message += ' '*1500
            return Response(message, status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        else:
            raise Exception('Channel is missing in parameter list')
    except queue.Empty as e:
        return Response('', status=408, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        logger.debug(f"dequeue_request exception {e!r}")
        e_message = e.response.text if e.response and e.response.text else ''
        return Response(e_message, status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of dequeue_request')

@app.route('/dequeue_reply', methods=['GET'])
def dequeue_reply():
    logger.debug('into dequeue_reply')
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
    except queue.Empty as e:
        return Response('', status=408, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        logger.debug(f"dequeue_reply exception {e!r}")
        e_message = e.response.text if e.response and e.response.text else ''
        return Response(e_message, status=500, content_type='text/plain', headers={'Access-Control-Allow-Origin': '*'})
    finally:
        logger.debug('out of dequeue_reply')

@app.route('/status', methods=['GET'])
def status():
    logger.debug(f'into status')

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
        logger.debug(f'out of status')


def _enqueue(operation, channel, msg):
    logger.debug(f' into _enqueue: {operation}, channel: {channel}, msg: {msg}')
    post, post_status = _verify_channel(channel, operation)
    try:
        post['lock'].acquire()
        if not post['q'].empty():
            raise Exception(f'Channel {channel} contains unprocessed message')
        if not post['qq'] is None:
            raise Exception(f'qq Channel {channel} contains unprocessed message')
        if not post_status['pickup_time'] is None:
            # Prior message was picked up, so get rid of waiter status
            post_status['pickup_wait'] = post_status['pickup_time'] = None
        post_status['posted_time'] = time.asctime()
        post_status['message'] = msg
        logger.debug(' put message ')
        if not post['qq'] is None: logger.debug('   qqPUT QUEUE IS NOT EMPTY')
#        post['q'].put(msg)
        post['qq'] = msg
        logger.debug(' put message done')
    finally:
        post['lock'].release()
        logger.debug(' out of _enqueue')

def _dequeue(operation, channel, reset_first):
    logger.debug(f' into _dequeue: {operation}, channel: {channel}, reset_first: {reset_first}')
    pickup, pickup_status = _verify_channel(channel, operation)
    try:
        try:
            pickup['lock'].acquire()
            if reset_first: # Clear out any (presumably dead) reader
                pickup['q'].put('dying breath') # Satisfy outstanding (dead?) reader
                pickup['q'] = queue.Queue() # Make double-sure queue is clean
                pickup['qq'] = None
            pickup_status['pickup_wait'] = time.asctime()
            pickup_status['pickup_time'] = None
            if pickup['qq'] is None: # clear out already-read message
                pickup_status['message'] = None
                pickup_status['posted_time'] = None
        finally:
            pickup['lock'].release()

        # Block if no message, and return message and queue empty. If blocked for a long time,
        # give caller the a timeout status and allow it to re-issue dequeue.
        try:
            logger.debug(' get message ')
            if not pickup['qq'] is None: logger.debug('   qqPICKUP QUEUE IS NOT EMPTY BEFORE')
#            msg = pickup['q'].get(timeout=DEQUEUE_TIMEOUT_SECS)
            dequeue_timeout_secs_left = DEQUEUE_TIMEOUT_SECS
            msg = pickup['qq']
            while msg is None and dequeue_timeout_secs_left > 0:
                time.sleep(1)
                dequeue_timeout_secs_left -= 1
                msg = pickup['qq']
            if msg is None:
                raise queue.Empty()

            #            if msg is None: raise queue.Empty()
            logger.debug(f'  dequeued: {operation}, channel: {channel}, msg: {msg}')
            try:
                pickup['lock'].acquire()
                # Don't erase pickup_wait here because it can be useful to see how long a response took
                pickup_status['pickup_time'] = time.asctime()
            finally:
                pickup['lock'].release()
        except queue.Empty as e:
#            if not pickup['q'].empty(): logger.debug('   PICKUP QUEUE IS NOT EMPTY AFTER EMPTY EXCEPTION')
            logger.debug(f'  dequeue timed out: {operation}, channel: {channel}')
            raise

    finally:
        logger.debug(' out of _dequeue')

    return msg

def _verify_channel(channel, operation):
    try:
        channel_status_lock.acquire()
        if not channel in channel_status:
            channel_status[channel] = {'request': {'q': queue.Queue(), 'qq': None, 'lock': threading.Lock(), 'status': empty_status.copy()},
                                       'reply'  : {'q': queue.Queue(), 'qq': None, 'lock': threading.Lock(), 'status': empty_status.copy()}}
    finally:
        channel_status_lock.release()

    return channel_status[channel][operation], \
           channel_status[channel][operation]['status']

if __name__=='__main__':
    debug = False
    if len(sys.argv) > 1:
        host_ip = sys.argv[1]
        debug = True
    else:
        host_ip = '0.0.0.0'
    app.run(debug=debug, host=host_ip)
