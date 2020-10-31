 /*
    These functions serve as a connector between a remote Jupyter server and Cytoscape.
    They run in the user's browser, which also shows the Jupyter Notebook.

    A remote Jupyter Notebook call to the py4cytoscape package is forwarded to the Jupyter Bridge,
    which is a standalone server. The functions in this connector execute in the Jupyter Notebook
    browser, which executes on the same PC as Cytoscape. So, that's 4 components: (A) remote
    Jupyter Notebook, (B) separate Jupyter Bridge server, (C) this browser-based component, and
    (D) Cytoscape. (A) is on a remote server, (B) is on a different remote server, and (C) and (D)
    are on the user's PC.

    (A) calls its py4cytoscape module, which forwards the request (in a JSON wrapper) to (B).
    (C) picks up the request from (B), unpacks the request and forwards it to (D). (C) awaits a
    reply from (D), and when it gets it, it forwards the reply (in a JSON wrapper) to (B).
    (A)'s py4cytoscape module picks up the reply on (B) when it becomes available, unpacks it,
    and returns it to (A).

    A Jupyter Notebook can talk to only one Cytoscape (i.e., the one on the machine running the
    Jupyter Notebook browser), and Cytoscape should be called by only one Jupyter Notebook. The
    Jupyter Bridge differentiates between Notebook-Cytoscape conversations via a channel UUID.
    The UUID is prepended to this browser component by py4Cytoscape, and the component is
    started by the Jupyter Notebook. (I wish py4Cytoscape could start the component, too, but I
    haven't figured out how to do that yet, so startup code *is* required in the Jupyter
    Notebook.)

    Note that for the case of a Jupyter server running on the same machine as Cytoscape, this
    bridge isn't necessary because the Jupyter server's HTTP calls can easily connect to
    Cytoscape over a localhost socket. So, the combination of Jupyter Bridge and this browser
    component solves the problem of a Jupyter server (e.g., Google's Colab) that can't
    connect to Cytoscape that sits behind a firewall.

    The request represents an HTTP call that py4cytoscape would normally make via HTTP directly
    to Cytoscape via localhost when both py4cytoscape and Cytoscape are running on the same machine.
 */

const VERSION = '0.0.2'

var showDebug; // Flag indicating whether to show Jupyter-bridge progress
if (typeof showDebug === 'undefined') {
    showDebug = false
}
if (showDebug) {
    alert("Starting Jupyter-bridge browser component")
}

//const JupyterBridge = 'http://127.0.0.1:5000' // for testing against local Jupyter-bridge
var JupyterBridge; // URL of Jupyter-bridge server could be defined by assignment pre-pended to this file
if (typeof JupyterBridge === 'undefined') {
    JupyterBridge = 'https://jupyter-bridge.cytoscape.org' // for production
}
var Channel; // Unique constant that could be defined by assignment pre-pended to this file
if (typeof Channel === 'undefined') { // ... but if not assigned, use a debugging value
    Channel = 1
}


var httpR = new XMLHttpRequest(); // for sending reply to Jupyter-bridge
var httpRE = new XMLHttpRequest(); // for sending backup error reply to Jupyter-bridge
var httpC = new XMLHttpRequest(); // for sending command to Cytoscape
var httpJ = new XMLHttpRequest(); // for fetching request from Jupyter-bridge

const HTTP_OK = 200
const HTTP_SYS_ERR = 500
const HTTP_TIMEOUT = 408
const HTTP_TOO_MANY = 429


 /* This function is useful if we want to rewrite the incoming URL to resolve just to our local one.
    Doing this stops the Jupyter component from abusing this client to call out to endpoints other
    than local Cytoscape. On the other hand, it makes it hard to detect when the Jupyter component
    has specified a genuinely bad URL and really should get an error result. For now, we'll execute
    the Jupyter-supplied URL and return the result, whatever it may be.

const LocalCytoscape = 'http://127.0.0.1:1234'

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
*/

function replyCytoscape(replyStatus, replyStatusText, replyText) {

    // Clean up after Jupyter bridge accepts reply
    httpR.onreadystatechange = function() {
        if (httpR.readyState === 4) {
            if (showDebug) {
                console.log(' status from queue_reply: ' + httpR.status + ', reply: ' + httpR.responseText)
            }
        }
    }

    httpR.onerror = function() {
        // Clean up after Jupyter bridge accepts backup reply
        httpRE.onreadystatechange = function() {
            if (httpRE.readyState === 4) {
                if (showDebug) {
                    console.log(' status from backup queue_reply: ' + httpRE.status + ', reply: ' + httpRE.responseText)
                }
            }
        }

        console.log(' error from queue_reply -- could be Jupyter-Bridge server reject')
        var errReply = {'status': HTTP_SYS_ERR, 'reason': '', 'text': 'Error returning response -- could be too long for Jupyter-Bridge server'}
        httpRE.open('POST', jupyterBridgeURL, true)
        httpRE.setRequestHeader('Content-Type', 'text/plain')
        httpRE.send(JSON.stringify(errReply))
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
                console.log(' status from CyREST: ' + httpC.status + ', statusText: ' + httpC.statusText + ', reply: ' + httpC.responseText)
            }
            // Note that httpC.status is 0 if the URL can't be reached *OR* there is a CORS violation.
            // I wish I could tell the difference because for a CORS violation, I'd return a 404,
            // which would roughly match what Python's native request package would return.
            // The practical consequence is that the ultimate caller (e.g., py4cytoscape)
            // returns different exceptions, depending on wither this module is doing the
            // HTTP operation or the native Python requests package is. This is minor, but
            // messes up tests that verify the exception type.
            replyCytoscape(httpC.status, httpC.statusText, httpC.responseText)
            waitOnJupyterBridge()
        }
    }

//  Build up request to Cytoscape, making sure host is local.
//    Too heavy handed: localURL = LocalCytoscape + parseURL(callSpec.url).pathname
    var localURL = callSpec.url // Try using what was passed in ... is there a security risk??

    if (showDebug) {
        console.log('Command to CyREST: ' + callSpec.command + ' (' + localURL + ')')
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

    if (callSpec.command === 'webbrowser') {
        if (window.open(callSpec.url)) {
            replyCytoscape(HTTP_OK, 'OK', '')
        } else {
            replyCytoscape(HTTP_SYS_ERR, 'BAD BROWSER OPEN', '')
        }
        waitOnJupyterBridge()
    } else if (callSpec.command === 'version') {
        replyCytoscape(HTTP_OK, 'OK',
            JSON.stringify({"jupyterBridgeVersion": VERSION}))
        waitOnJupyterBridge()
    } else {
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
}

function waitOnJupyterBridge() {

    // Captures request from Jupyter bridge
    httpJ.onreadystatechange = function() {
        if (httpJ.readyState === 4) {
            if (showDebug) {
                console.log(' status from dequeue_request: ' + httpJ.status + ', reply: ' + httpJ.responseText)
            }
            try {
                if (httpJ.status == HTTP_TOO_MANY) {
                    // Nothing more to do ... the browser has created too many listeners,
                    // and it's time to stop listening because the server saw a listener
                    // listening on this channel before we got there.
                    console.log('  shutting down because of redundant reader on channel: ' + Channel)
                } else {
                    if (httpJ.status === HTTP_TIMEOUT) {
                        waitOnJupyterBridge()
                    } else {
                        callCytoscape(JSON.parse(httpJ.responseText))
                    }
                }
            } catch(err) {
                if (showDebug) {
                    console.log(' exception calling Cytoscape: ' + err)
                }
                // Bad responseText means something bad happened that we don't understand.
                // Go wait on another request, as there's nothing to call Cytoscape with.
                waitOnJupyterBridge()
            }
        }
    }

    // Wait for request from Jupyter bridge
    var jupyterBridgeURL = JupyterBridge + '/dequeue_request?channel=' + Channel
    if (showDebug) {
        console.log('Starting dequeue on Jupyter bridge: ' + jupyterBridgeURL)
    }
    httpJ.open('GET', jupyterBridgeURL, true)
    httpJ.send()
}

// This kicks off a loop that ends by calling waitOnJupyterBridge again. This first call
// ejects any dead readers before we start a read
waitOnJupyterBridge() // Wait for message from Jupyter bridge, execute it, and return reply

if (showDebug) {
    alert("Jupyter-bridge browser component is started on " + JupyterBridge + ', channel ' + Channel)
}
