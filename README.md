# Jupyter-bridge


Jupyter-bridge is a Flask service that executes on a server accessible to both a remote Jupyter server and browser-based
Jupyter client. Code running on the server calls Jupyter-bridge to queue a request that the client will execute, and the
client will use Jupyter-bridge to return a reply. This enables a workflow running on remote Jupyter to execute functions
on a PC-local Cytoscape -- the remote Jupyter runs the request through Jupyter-bridge, where it is picked up by 
Javascript code running on the Jupyter web page in the PC-local browser, which in turn calls Cytoscape. The Cytoscape
response travels the reverse route.

This is almost possible via the Jupyter server's %%javascript magic combined with the PC-based browser client's 
IPython.notebook.kernel.execute() function, except that the server won't see the reply until all cells are 
executed -- too late.

A channel is identified as a UUID that both the client (PC-based browser) and server (remote Jupyter) share before 
trying to use this bridge. Initially, the client waits on a request on that channel, and the server eventually 
sends a request to it. The client then receives the request and executes the HTTP operation (i.e., a call to Cytoscape)
identified in the request. The server waits for a reply on that channel, and the client sends it when the HTTP operation
is complete (i.e., Cytoscape returns an answer). The request and reply operations are symmetrical, and so share 
common code. However, the request operation saves the request in a request map (keyed by channel ID), and the 
reply operation saves the reply in a reply map.

Queuing requests is not allowed. If the server sends a request before the client operates on it, an error occurs.
Likewise, when the client sends a reply, it assumes the server will receive it before the client needs to send a
subsequent reply.

The database for requests and replies is implemented as an external redis server, which provides a single source of 
truth regardless of how many Flash processes run concurrently. The opposite of this would be that the Flask service
keeps its own global data structure, but that would be infeasible because each process has its own copy of the data. 
An example of a failure would be posting a request in one process' data structure and trying to retrieve it from a
different process' data structure.

Requests are assumed to be a JSON structure that describes the Cytoscape HTTP call. Replies are assumed to be the
raw text returned by Cytoscape, and may include JSON that will be recovered by the requestor when it receives the
reply.
