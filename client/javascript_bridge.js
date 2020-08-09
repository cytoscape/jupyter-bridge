alert("hi from testjs https start")

    /*
    These functions serve as a bridge between a remote Jupyter server and Cytoscape. They proxy
    the Jupyter server's HTTP calls (coming from a Jupyter Notebook with py4cytoscape) to
    Cytoscape's CyREST layer. Note that for the case of a Jupyter server running on the same
    machine as Cytoscape, this bridge isn't necessary because the Jupyter server's HTTP calls
    can easily connect to Cytoscape over localhost. So, this bridge solves the problem of
    a Jupyter server (e.g., Google's Colab) that can't connect to Cytoscape that sits behind
    a firewall.

    At a high level, py4cytoscape running in a remote Jupyter server sends its request to
    the Jupyter Bridge, which holds the request until this Javascript Bridge picks it up. The
    Javascript Bridge fulfills the request by making an HTTP request to Cytoscape's CyREST. When
    it gets a result, it passes it back to Jupyter Bridge, and py4cytoscape picks it up and
    and continues execution of the Notebook.

    The request represents an HTTP call that py4cytoscape would normally make via HTTP directly
    to Cytoscape via localhost when both py4cytoscape and Cytoscape are running on the same machine.
    The possible requests are:

    GET(url, params) - may return plain text or JSON
    POST(url, params, body as JSON) - may return plain text or JSON
    POST(url, data as JSON, headers as {'Content-Type': 'application/json', 'Accept': 'application/json'} - returns JSON
    PUT(url, params, body as JSON) - may return plain text or JSON
    DELETE(url, params)

    To handle this:
    * The URL is rewritten to be http://localhost:1234
    * The params is passed in as stringified JSON
    * The body is passed in as stringified JSON
    * The data is passed in as stringified JSON
    * Headers are passed in as stringified JSON
    * Data and status are passed back as text and interpreted by the caller

    Unhandled requests (so far):
    webbrowser.open()

     */


//const JupyterBridge = 'http://127.0.0.1:5000' // for testing against local Jupyter-bridge
const JupyterBridge = 'https://jupyter-bridge.cytoscape.org' // for production
var Channel; // Large number that could be defined by assignment pre-pended to this file
if (typeof Channel === 'undefined') { // ... but if not assigned, use a debugging value
    Channel = 1
}

const LocalCytoscape = 'http://127.0.0.1:1234'

var httpR = new XMLHttpRequest();; // for sending reply to Jupyter-bridge
var httpC = new XMLHttpRequest();; // for sending command to Cytoscape
var httpJ = new XMLHttpRequest();; // for fetching request from Jupyter-bridge

var showDebug = true


function parseURL(url) {
    var reURLInformation = new RegExp([
        '^(https?:)//', // protocol
        '(([^:/?#]*)(?::([0-9]+))?)', // host (hostname and port)
        '(/{0,1}[^?#]*)', // pathname
        '(\\?[^#]*|)', // search
        '(#.*|)$' // hash
    ].join(''));
    var match = url.match(reURLInformation);
    return match && {
        url: url,
        protocol: match[1],
        host: match[2],
        hostname: match[3],
        port: match[4],
        pathname: match[5],
        search: match[6],
        hash: match[7]
    }
}


function replyCytoscape(replyStatus, replyStatusText, replyText) {

    // Clean up after Jupyter bridge accepts reply
    httpR.onreadystatechange = function() {
        if (httpR.readyState === 4) {
            if (showDebug) {
                console.log(' status: ' + httpR.status + ', reply: ' + httpR.responseText)
            }
        }
    }

    var reply = {'status': replyStatus, 'reason': replyStatusText, 'text': replyText}

    // Send reply to Jupyter bridge
    var jupyterBridgeURL = JupyterBridge + '/queue_reply?channel=' + Channel
    if (showDebug) {
        console.log('Starting queue to Jupyter bridge: ' + jupyterBridgeURL)
    }
    httpR.open('POST', jupyterBridgeURL, true)
    httpR.setRequestHeader('Content-Type', 'text/plain')
    httpR.send(JSON.stringify(reply))
}

function callCytoscape(callSpec) {

    // Captures Cytoscape reply and sends it on
    httpC.onreadystatechange = function() {
        if (httpC.readyState === 4) {
            if (showDebug) {
                console.log(' status: ' + httpC.status + ', statusText: ' + httpC.statusText + ', reply: ' + httpC.responseText)
            }
            // Note that httpC.status is 0 if the URL can't be reached *OR* there is a CORS violation.
            // I wish I could tell the difference because for a CORS violation, I'd return a 404,
            // which would roughly match what Python's native request package would return.
            // The practical consequence is that the ultimate caller (e.g., py4cytoscape)
            // returns different exceptions, depending on wither this module is doing the
            // HTTP operation or the native Python requests package is. This is minor, but
            // messes up tests that verify the exception type.
            replyCytoscape(httpC.status, httpC.statusText, httpC.responseText)
            waitOnJupyterBridge(false)
        }
    }

    // Build up request to Cytoscape, making sure host is local
//    too heavy handed: localURL = LocalCytoscape + parseURL(callSpec.url).pathname
    var localURL = callSpec.url // Try using what was passed in ... is there a security risk??

    if (showDebug) {
        console.log('Command: ' + callSpec.command + ' (' + localURL + ')')
        if (callSpec.params) {
            console.log(' params: ' + JSON.stringify(callSpec.params))
        }
        if (callSpec.headers) {
            console.log(' header: ' + JSON.stringify(callSpec.headers))
        }
        if (callSpec.data) {
            console.log('   data: ' + JSON.stringify(callSpec.data))
        }
    }

    var joiner = '?'
    for (let param in callSpec.params) {
        localURL = localURL + joiner + param + '=' + encodeURIComponent(callSpec.params[param])
        joiner = '&'
    }

    httpC.open(callSpec.command, localURL, true)
    for (let header in callSpec.headers) {
        httpC.setRequestHeader(header, callSpec.headers[header])
    }

    // Send request to Cytoscape ... reply goes to onreadystatechange handler
    httpC.send(JSON.stringify(callSpec.data))
}

function waitOnJupyterBridge(resetFirst) {

    // Captures request from Jupyter bridge
    httpJ.onreadystatechange = function() {
        if (httpJ.readyState === 4) {
            if (showDebug) {
                console.log(' status: ' + httpJ.status + ', reply: ' + httpJ.responseText)
            }
            try {
                if (httpJ.status === 408) {
                    waitOnJupyterBridge(false)
                } else {
                    callCytoscape(JSON.parse(httpJ.responseText))
                }
            } catch(err) {
                if (showDebug) {
                    console.log(' exception calling Cytoscape: ' + err)
                }
                // Bad responseText means something bad happened that we don't understand.
                // Go wait on another request, as there's nothing to call Cytoscape with.
                waitOnJupyterBridge(false)
            }
        }
    }

    // Wait for request from Jupyter bridge
    var jupyterBridgeURL = JupyterBridge + '/dequeue_request?channel=' + Channel
    if (resetFirst) {
        jupyterBridgeURL = jupyterBridgeURL + '&reset'
    }
    if (showDebug) {
        console.log('Starting dequeue on Jupyter bridge: ' + jupyterBridgeURL)
    }
    httpJ.open('GET', jupyterBridgeURL, true)
    httpJ.send()
}

// This kicks off a loop that ends by calling waitOnJupyterBridge again. This first call
// ejects any dead readers before we start a read
waitOnJupyterBridge(true) // Wait for message from Jupyter bridge, execute it, and return reply


alert("hi from testjs https end " + JupyterBridge)