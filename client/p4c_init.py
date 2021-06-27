# Install py4cytoscape module and start Jupyter-Bridge web client
#
# This code enables Notebook-based py4cytoscape to communicate with Cytoscape via
# Jupyter-Bridge. It should be called in a notebook cell before any other
# py4cytoscape functions, and the caller must execute the following statement
# as the last statement in the cell:
#
#    IPython.display.Javascript(_PY4CYTOSCAPE_BROWSER_CLIENT_JS)
#
# So, the calling cell would look something like this:
#
#    import requests
#    exec(requests.get("https://raw.githubusercontent.com/cytoscape/jupyter-bridge/master/client/p4c_init.py").text)
#    IPython.display.Javascript(_PY4CYTOSCAPE_BROWSER_CLIENT_JS) # Start browser client
#
# This code can be customized by setting variables ahead of the exec() call. Specifically:
#
# * _PY4CYTOSCAPE ... names the actual module to be loaded (default: py4cytocape in PyPI)
# * _PY4CYTOSCAPE_DEBUG_BROWSER ... True browser debug console output (default: False)
#
# Examples of plausible _PY4CYTOSCAPE values:
#
# * Github master: 'git+https://github.com/cytoscape/py4cytoscape'
# * Github 0.0.10 branch: 'git+https://github.com/cytoscape/py4cytoscape@0.0.10'
#
# Note that with the exception of _PY4CYTOSCAPE_BROWSER_CLIENT_JS, this code's variables
# are not intended to be accessed by user code.
#
# Note that due to the brittleness of the IPython.display.Javascript()
# function, it must be the last statement in the cell, not the last
# statement in the last block (e.g., try-except or if-then) ... really ... it must
# be the *last* statement in the cell.
#
# This code creates the Jupyter-Bridge javascript functions that implement the
# Jupyter-Bridge web client, and encodes them in the _PY4CYTOSCAPE_BROWSER_CLIENT_JS
# variable. Along the way, it creates a communication channel ID that will be shared
# by py4cytoscape and the web client to communicate through Jupyter-Bridge and embeds
# it directly in the web client code. The web client code used the channel ID when
# polling Jupyter-Bridge for a message from py4cytoscape to Cytoscape.
#
# This code is a bit involved because it handles multiple cases:
# * Works with both Jupyter Notebooks and Google Colaboratory Notebooks
# * Allows this code to be called multiple times over the Python kernel's lifetime
#
# One difference between Jupyter Notebooks and Colab is in the "--user" parameter
# for the pip command. Jupyter assumes the notebook is executing in a multi-user
# system, and so modules should be installed on a user-by-user basis. Colab assumes
# that the notebook is executing in its own virtual machine, and there is only one
# user for the entire VM. So, pip under Jupyter Notebooks needs "--user", and Colab
# rejects it.
#
# Another difference is in how each system treats the javascript code that comprises
# the web client. Jupyter Notebook will create a separate instance of the web
# client each time IPython.display.Javascript(_PY4CYTOSCAPE_BROWSER_CLIENT_JS)
# is called (i.e., whenever the calling cell is re-executed). Recall that each
# web client uses a different channel ID to poll Jupyter-Bridge. But py4cytoscape
# uses only the most recently created channel ID -- meaning that previous web client
# instances using previous channel IDs are zombies because they poll on channels
# that py4cytoscape will never use. Nevertheless, they continue to poll because
# there is no (good) way to deactivate them. This code seeks to avoid creating
# zombies by creating only a web client only the first time it's called, and
# creating null web clients for successive calls.
#
# A zombie web client (were it to be created) carries no consequence for py4cytoscape
# functions, except that Jupyter-Bridge communications slow down due to unproductive
# polling. Despite this code's attempt to avoid creating zombie web clients, zombies
# are created when the user restarts the Python kernel and then re-executes this
# code. The only way to purge such zombies is to restart the browser and then
# re-execute this code's calling cell. The true need for this is a matter for the
# user's tolerance for the (small) zombie-related slowdown.
#
# The situation would be the same for Colab, but for a severe bug that apparently
# affects IPython.display.Javascript() call. The first call successfully starts the
# web client, but successive calls terminate all code loaded by
# IPython.display.Javascript() either now or in the past. (Recall that this code
# tries to avoid zombie calls by arranging for only the first
# IPython.display.Javascript() call to start a web client, and then subsequent calls
# to start a null web client.) This is especially problematic because the
# IPython.display.Javascript() code must be the *last* code in the calling cell -- it
# cannot be conditionally executed or avoided in any way. So, even starting a
# null web client terminates a running web client. The end result is that the
# first call sets up the web client, and subsequent calls kill it.
#
# So, whereas this call is resilient against multiple executions in a Jupyter Notebook
# environment, multiple executions under Colab are fatal. The only choice is to alert
# the user when a second call is attempted, and ask for a manual kernel restart.
#

import IPython, sys

_PY4CYTOSCAPE_RUNNING_IN_COLAB = 'google.colab' in str(get_ipython())
_PY4CYTOSCAPE_MODULE_SPACE = '' if _PY4CYTOSCAPE_RUNNING_IN_COLAB else '--user'

# Install py4cytoscape module into python space
if 'py4cytoscape' not in sys.modules: # Check to see if py4cytoscape already loaded
  # No ... if module name not already defined by user, choose default module name
  if "_PY4CYTOSCAPE" not in globals(): _PY4CYTOSCAPE = 'py4cytoscape'
        
  # If Colab, module is installed at system level. If Notebook, module is in user-space  
  get_ipython().run_line_magic('run', '-m pip install ' + _PY4CYTOSCAPE_MODULE_SPACE + ' ' + _PY4CYTOSCAPE)

import py4cytoscape as p4c

# Start the Jupyter-Bridge to enable communication with Cytoscape on workstation
if "_PY4CYTOSCAPE_CHANNEL" in globals():
  # py4cytoscape web client has already been started ... don't start another
  if _PY4CYTOSCAPE_RUNNING_IN_COLAB:
    error = 'Re-initialization does not work properly in Colab.  Do Runtime | Factory Reset Runtime on the Colab menu, and then restart your notebook.'
    print(error)
    exit()
    raise Exception(error)
  else:
    print(f'Skip reloading Javascript client ... {_PY4CYTOSCAPE_CHANNEL} on {p4c.get_jupyter_bridge_url()}')
  _PY4CYTOSCAPE_BROWSER_CLIENT_JS = '' # Add nothing to the browser's Javascript
else:
  # py4cytoscape web client needs to be loaded ... generate code and prepare it for loading
  if "_PY4CYTOSCAPE_DEBUG_BROWSER" not in globals():  _PY4CYTOSCAPE_DEBUG_BROWSER = False
  _PY4CYTOSCAPE_BROWSER_CLIENT_JS = p4c.get_browser_client_js(_PY4CYTOSCAPE_DEBUG_BROWSER)
  _PY4CYTOSCAPE_CHANNEL = p4c.get_browser_client_channel()
  print(f'Loading Javascript client ... {_PY4CYTOSCAPE_CHANNEL} on {p4c.get_jupyter_bridge_url()}')
  if _PY4CYTOSCAPE_RUNNING_IN_COLAB:
    print('ADVICE: WHEN RUNNING UNDER COLAB, DO NOT RE-RUN THIS CELL WITHOUT MANUALLY EXECUTING Runtime | Factory Reset Runtime FROM THE COLAB MENU FIRST.')

# Caller must do this part: IPython.display.Javascript(_PY4CYTOSCAPE_BROWSER_CLIENT_JS) # Start browser client