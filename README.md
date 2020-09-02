# Jupyter-Bridge
Jupyter-Bridge is a Flask service that executes on a server accessible to both a remote Jupyter server and browser-based
Jupyter client. Code running on the server calls Jupyter-Bridge to queue a request that the client will execute, and the
client will use Jupyter-Bridge to return a reply. This enables a workflow running on remote Jupyter to execute functions
on a PC-local Cytoscape -- the remote Jupyter runs the request through Jupyter-Bridge, where it is picked up by 
Javascript code running on the Jupyter web page in the PC-local browser, which in turn calls Cytoscape. The Cytoscape
response travels the reverse route.

## The Problem
Currently, a Python-based workflow can leverage Cytoscape features by calling Cytoscape via py4cytoscape/CyREST over a 
channel created on localhost (see below). This means that the workflow must be executing on the same workstation as 
Cytoscape (either as workstation-based standalone Python or Notebook).

![Figure 1](docs/images/Figure%201.svg)

Because of network security (e.g., firewalls), there is no general way for a workflow executing in a remote server-based Jupyter Notebook to leverage your workstation’s Cytoscape. This makes it hard to share notebook-based workflows and data sets.

## The Solution
Jupyter-Bridge allows a remote Jupyter Notebook to communicate with a workstation-based Cytoscape as if the Notebook were running on the Cytoscape workstation. A Jupyter Notebook passes a Cytoscape call to an independent Jupyter-Bridge server where it’s picked up by the Jupyter-Bridge browser component and is passed to Cytoscape. The Cytoscape response is returned via the opposite flow. As a result, workflows can reside in the cloud, access cloud resources, and yet still leverage Cytoscape features (see below). 

![Figure 2](docs/images/Figure%202.svg)

The Jupyter-Bridge components are shown in green – the browser component is attached to each Jupyter Notebook’s browser window, and there is a single Jupyter-Bridge server always running in the cloud.

As with py4cytoscape running on a workstation, each remote py4cytoscape can pair with only one local Cytoscape, and each local Cytoscape can pair with only that remote py4cytoscape. Jupyter-Bridge enforces this by assigning a unique, secret temporary ID to a local Cytoscape instance, and it shares that ID with only one remote py4cytoscape.

→ _Bonus Question:_ Why couldn’t this have been done via a `%%javascript` cell in any Jupyter Notebook?? _Answer:_ The Cytoscape call could have, but because of the way Jupyter manages its ZeroMQ queues, the Cytoscape reply could not be returned to the workflow until after all cells had finished executing. Cytoscape workflows need the reply for one request before it can proceed to the next.

## Trying out Jupyter-Bridge
You can quickly test the connection between a remote Jupyter Notebook and a Cytoscape running on your workstation by following these steps:

1. Create a new Python 3.7+ Jupyter Notebook on a remote server (e.g., GenePattern Notebook, Google Colab, etc) and start Cytoscape on the local workstation.

2. Create and execute a cell with the following content: 

        import sys, IPython
        !{sys.executable} -m pip uninstall -y py4cytoscape
        
        # Uncomment this to install the development py4cytoscape
        # !{sys.executable} -m pip install --upgrade git+https://github.com/cytoscape/py4cytoscape
        
        # Comment this out to avoid installing the release py4cytoscape
        !{sys.executable} -m pip install --upgrade py4cytoscape
        
        import py4cytoscape as p4c
        print(f'Loading Javascript client ... {p4c.get_browser_client_channel()} on {p4c.get_jupyter_bridge_url()}')
        browser_client_js = p4c.get_browser_client_js()
        IPython.display.Javascript(browser_client_js) # Start browser client

This will import the latest py4cytoscape module, then start the Jupyter-Bridge browser component. 

3. Create and execute a cell with the following content:

        print(dir(p4c))
        p4c.cytoscape_version_info()

This will demonstrate that a connection exists between the remote Jupyter Notebook and local Cytoscape.

## Configuration
Using the [installation](#installation) instructions below, you can create your own Jupyter-Bridge server addressable
in your own domain. Once this server is running you can direct your Jupyter Notebook to use it
by setting the JUPYTER_BRIDGE_URL environment variable for your notebook. The default value is
https://jupyter-bridge.cytoscape.org. So long as the prefix is 'https:', you can choose whatever
domain your server answers to. 

# Discussion
The Jupyter-Cytoscape link is *almost* possible via the Jupyter server's %%javascript magic combined with the 
PC-based browser client's IPython.notebook.kernel.execute() function, except that the server won't see the 
reply until all cells are executed -- too late.

The client (PC-based browser on the same workstation as Cytoscape) and server (remote Jupyter running a 
Python-based py4cytoscape workflow) create a connection identified by a shared UUID. Initially, the client waits 
on a request on that channel, and the server eventually sends a request to it. The client then receives the 
request and executes the HTTP operation identified in the request (i.e., as a call to Cytoscape/CyREST). 
When Cytoscape responds, the client sends the reply to the server waiting on that channel. The request and reply
operations are symmetrical, and so share common code.

Queuing requests is not allowed. If the server sends a request before the client operates on it, an error occurs.
Likewise, when the client sends a reply, it assumes the server will receive it before the client needs to send a
subsequent reply.

The state of each channel is maintained by the Jupyter-Bridge running on an independent cloud server. Because
Jupyter-Bridge can service multiple channels simultaneously, it is multi-threaded ... a thread is started to service
posting a request or reply, and fetching the request or reply. Requests and replies are stored in a Redis database
common to all threads.

Requests are assumed to be a JSON structure that describes the Cytoscape HTTP call. Replies are assumed to be the
raw text returned by Cytoscape, and may include JSON that will be recovered by the requestor when it receives the
reply.

# Endpoints
All service endpoints are accessible via Javascript running in a standard browser (and are therefore limited to HTTP 
GET and POST). Endpoints available via HTTP GET can be invoked from the address bar of a browser.
It's possible for a Jupyter-Bridge instance to be installed and reachable via any URL (see [installation](#installation)
instructions below). For the sake of this documentation, we assume the canonical https://jupyter-bridge.cytoscape.org URL.

## Channels
Endpoints that queue and dequeue requests and replies accept a `channel` parameter, which clients can use
to distinguish a message flow from flows for other clients. A message flow (request or reply) for a given channel is
maintained for up to 24 hours before Jupyter-Bridge declares it to be abandoned, and drops it. When a Jupyter-Bridge
instance restarts, it drops all message flows and starts afresh.

## Calling Sequence
The following diagram shows how messaging flows through the Jupyter-Bridge system, beginning with 
a running Notebook and spanning to Cytoscape and back. Note that the Jupyter-Bridge role is
in bold, and calls to the Jupyter-Bridge endpoints are also in bold. The endpoints are described in 
sections below.

![Calling Sequence1](docs/images/Sequence.pdf) 

## GET https://jupyter-bridge.cytoscape.org/ping
Returns the version identifier (e.g., "pong 0.0.2") of the Jupyter-Bridge instance.

## GET https://jupyter-bridge.cytoscape.org/stats
Returns a CSV file ("jupyter-bridge.csv") containing daily request and reply statistics statistics. This endpoint is
intended to be called from a browser that can then load the CSV into a spreadsheet program.

## POST https://jupyter-bridge.cytoscape.org/queue_request?channel=<uuid>
Accepts a payload that is saved for a client that will receive it by calling the `dequeue_request` endpoint with
the same `channel` argument. While the payload can be any JSON, clients generally exchange JSON similar to:

    {"command": "GET",
     "url": "http://127.0.0.1:1234/v1,
     "params": null,
     "data": null,
     "headers": ["Accept: application/json"]
    }

This endpoint does not queue requests. If a request is received before a client receives (and acts on) a pending reply,
the prior reply will be lost and a log entry will be made.

## POST https://jupyter-bridge.cytoscape.org/queue_reply?channel=<uuid>
Accepts a payload that is saved for a client that will receive it by calling the `dequeue_reply` endpoint with the same
`channel` argument. The payload can be any text or JSON, and a sample JSON is:

    {"apiVersion": "v1",
     "cytoscapeVersion": "3.8.1"
    }

This endpoint does not queue replies. If a reply is received before a client receives (and acts on) a prior reply,
the prior reply will be ignored and an error will be returned.

## GET https://jupyter-bridge.cytoscape.org/dequeue_request?channel=<uuid>
Returns a payload posted as a request by calling the `queue_request` endpoint with the same `channel` argument. 

This endpoint waits up to 15 seconds for a reply to be posted before returning an HTTP 408 status. The client should
retry this endpoint until a reply is finally available.

If this endpoint detects that two clients are waiting on a reply for the same channel, it returns an HTTP 429 status.
The client should discontinue calling this endpoint. (This situation could happen if the browser allows multiple 
threads to execute the same Jupyter-Bridge browser component code, as could happen if py4cytoscape is initialized 
multiple time on the same browser page.)
   
## GET https://jupyter-bridge.cytoscape.org/dequeue_reply?channel=<uuid>
Returns a payload posted as a reply by calling the `queue_reply` endpoint with the same `channel` argument. 

This endpoint waits up to 15 seconds for a reply to be posted before returning an HTTP 408 status. The client should
retry this endpoint until a reply is finally available.

If this endpoint detects that two clients are waiting on a reply for the same channel, it returns an HTTP 429 status.
The client should discontinue calling this endpoint. (This situation should never happen.)

# Installation
Jupyter-Bridge comes in two parts: the Jupyter-Bridge server and the browser component. This 
section describes how to create a Jupyter-Bridge server. There is no installation procedure
for the browser component -- it is automatically injected into the Jupyter Notebook web 
page when the Notebook imports py4cytoscape.

Also, for users, there is no need to create a Jupyter-Bridge server, as the Cytoscape project's
Jupyter-Bridge server is always available (at https://jupyter-bridge.cytoscape.org) and is 
pre-configured into py4cytoscape.

If you would like to create your own Jupyter-Server or rebuild the Cytoscape project's server, see below.
Note that these instructions are for re-creating the Cytoscape project's server. To create your own, 
you'll need a URL and SSL certificate for it, and then apply them where they're called for.

1. Create Ubuntu 18.04LTS with 15GB disk, 6GB RAM.

1. Install linux packages
 
   1. sudo apt update
   1. sudo apt install nginx
   1. sudo apt install git
   1. sudo apt install redis-server
   1. sudo apt install python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools

1. Finish installing redis

   1. In /etc/redis/redis.conf, change supervised no to supervised systemd
   1. sudo systemctl enable redis-server
   1. redis-cli
      1. ping (response PONG)
      1. quit
   1. Restart linux to verify (using redis-cli) that redis restarts on reboot
   
1. Finish installing nginx

   1. sudo systemctl enable nginx
   1. From browser: http://<server ip>
   1. Restart linux to verify (using browser) than nginx restarts on reboot

1. Adjust firewall

   1. sudo ufw allow 'Nginx Full'
   1. sudo ufw allow 22/tcp
   1. sudo ufw enable
   1. sudo ufw status
      1. should show both Nginx Full and Nginx Full (V6) allowd
   1. From browser: http://<server ip>
    
1. Install Jupyter-Bridge project

   1. cd ~
   1. git clone https://github.com/cytoscape/jupyter-bridge
   1. chmod +x jupyter-bridge/dev/*.sh
   1. Install nginx files
      1. sudo cp ~/jupyter-bridge/server/nginx-config/jupyter-bridge.cytoscape.org /etc/nginx/sites-available/
      1. sudo ln -s /etc/nginx/sites-available/jupyter-bridge.cytoscape.org /etc/nginx/sites-enabled/
      1. In /etc/nginx/ sites-available/ jupyter-bridge.cytoscape.org
         1. Change /home/bdemchak to whatever ~ resolves to
         1. Note that /etc/letsencrypt lines are present and are commented out … they will be changed when a key exists
            
1. Install certificate

   1. If you have your own certificate for jupyter-bridge.cytoscape.org, install it into certificate directory and edit /etc/nginx/sites-available/jupyter-bridge.cytoscape.org
   1. Otherwise, follow the process in https://phoenixnap.com/kb/letsencrypt-nginx
   1. From browser: https://jupyter-bridge.cytoscape.org
      1. Response should be “502 Bad Gateway”

1. Create Python Virtual Environment

   1. pip3 install virtualenv
   1. python3 -m virtualenv jupyter-bridge-env
   1. source jupyter-bridge-env/bin/activate
   1. pip install wheel
   1. pip install uwsgi flask redis requests
   1. deactivate

1. Install uWSGI

   1. sudo cp jupyter-bridge/server/uWSGI-config/jupyter-bridge.service /etc/systemd/system/
   1. sudo vi /etc/systemd/system/jupyter-bridge.service
      1. Change /home/bdemchak to whatever ~ resolves to
      1. Change User=bdemchak to your user name

1. Start Jupyter-Bridge

   1. sudo systemctl start jupyter-bridge
   1. sudo systemctl enable jupyter-bridge
   1. sudo systemctl status juptyer-bridge

1. Test Juptyer-bridge

   1. Using a browser: https://jupyter-bridge.cytoscape.org/ping
      1. Response should be “pong x.x.x” where x.x.x is the jupyter-bridge version 
   1. juptyer-bridge/dev/run-tests.sh
      1. Run should take 3 minutes
   1. Reboot and repeat the above

# Administration
Jupyter-Bridge requires no administration. However, it is open to inspection.

To view the status of a channel:

1. Start redis-cli from a terminal window
1. keys '*' -- shows all channels. Channels appear in pairs, with ':request' and ':reply' appended to <channel>
2. hgetall <channel>:request or <channel>:reply 

Note that all channels expire and are removed automatically 24 hours after they are last written to.

There are several useful scripts in jupyter-bridge/dev:

| Script | Use |
| :--- | :--- |
|  restart-nginx.sh | Restarts nginx – should be rarely/never needed  |
| restart-uwsgi.sh   | Restarts Jupyter-Bridge – clears log files, too |
| show-uwshi-log.sh   | Dumps Jupyter-Bridge log file to console |
| run-tests.sh   | Tests that Juptyer-bridge is running – takes 3 min |
| git-jupyter-bridge.sh   | Clears out existing Juptyer-Bridge and clones anew |


There are several useful logs:

| Log | Use |
| :--- | :--- |
|  /var/log/nginx/*.log | nginx connect/error logs  |
| /var/log/redis/redis-server.log   | redis liveness log |
| ~/jupyter-bridge/server/jupyter-bridge.log   | record of all requests/replies to jupyter/bridge |
| In Jupyter Notebook: logs/py4cytoscape.log   | record of all py4cytoscape requests/replies |
| In browser console: let showDebug=true   | record of all browser interactions with Jupyter-Bridge and CyREST |


# License
Jupyter-Bridge is released under the MIT License (see [LICENSE](LICENSE) file):

```
    Copyright (c) 2018-2020 The Cytoscape Consortium
    Barry Demchak <bdemchak@ucsd.edu>
```
