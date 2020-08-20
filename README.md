# Jupyter-bridge
Jupyter-bridge is a Flask service that executes on a server accessible to both a remote Jupyter server and browser-based
Jupyter client. Code running on the server calls Jupyter-bridge to queue a request that the client will execute, and the
client will use Jupyter-bridge to return a reply. This enables a workflow running on remote Jupyter to execute functions
on a PC-local Cytoscape -- the remote Jupyter runs the request through Jupyter-bridge, where it is picked up by 
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
        !{sys.executable} -m pip install --upgrade git+https://github.com/bdemchak/py4cytoscape
        import py4cytoscape as p4c
        print('Loading Javascript client ... ' + str(p4c.get_browser_client_channel()))
        browser_client_js = p4c.get_browser_client_js()
        IPython.display.Javascript(browser_client_js) # Start browser client

This will import the latest py4cytoscape module, then start the Jupyter-Bridge browser component. 

3. Create and execute a cell with the following content:

        print(dir(p4c))
        p4c.cytoscape_version_info()

This will demonstrate that a connection exists between the remote Jupyter Notebook and local Cytoscape.

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


The state of each channel is maintained by the Jupyter-bridge running on an independent cloud server. Because
Jupyter-bridge can service multiple channels simultaneously, it is multi-threaded ... a thread is started to service
posting a request or reply, and fetching the request or reply. Requests and replies are stored in a Redis database
common to all threads.

Requests are assumed to be a JSON structure that describes the Cytoscape HTTP call. Replies are assumed to be the
raw text returned by Cytoscape, and may include JSON that will be recovered by the requestor when it receives the
reply.
