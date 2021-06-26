import IPython, sys

_PY4CYTOSCAPE_RUNNING_IN_COLAB = 'google.colab' in str(get_ipython())

# Install py4cytoscape module into python space
if 'py4cytoscape' not in sys.modules: # Check to see if py4cytoscape already loaded
  # No ... if module name not already defined by user, choose default module name
  if "_PY4CYTOSCAPE" not in globals(): _PY4CYTOSCAPE = 'py4cytoscape'
        
  # If Colab, module is installed at system level. If Notebook, module is in user-space  
  _PY4CYTOSCAPE_MODULE_SPACE = '' if _PY4CYTOSCAPE_RUNNING_IN_COLAB else '--user'
  get_ipython().run_line_magic('run', '-m pip install ' + _PY4CYTOSCAPE_MODULE_SPACE + ' ' + _PY4CYTOSCAPE)

import py4cytoscape as p4c

# Start the Jupyter-Bridge to enable communication with Cytoscape on workstation
if "_PY4CYTOSCAPE_CHANNEL" in globals():
  if _PY4CYTOSCAPE_RUNNING_IN_COLAB:
    print('Re-initialization does not work properly in Colab.  Do Runtime | Factory Reset Runtime on the Colab menu, and then restart your notebook.')
    exit()
    raise Exception
  else:
    print(f'Skip reloading Javascript client ... {_PY4CYTOSCAPE_CHANNEL} on {p4c.get_jupyter_bridge_url()}')
  _PY4CYTOSCAPE_BROWSER_CLIENT_JS = '' # Add nothing to the browser's Javascript
else:
  if "_PY4CYTOSCAPE_DEBUG_BROWSER" not in globals():  _PY4CYTOSCAPE_DEBUG_BROWSER = False
  _PY4CYTOSCAPE_BROWSER_CLIENT_JS = p4c.get_browser_client_js(_PY4CYTOSCAPE_DEBUG_BROWSER)
  _PY4CYTOSCAPE_CHANNEL = p4c.get_browser_client_channel()
  print(f'Loading Javascript client ... {_PY4CYTOSCAPE_CHANNEL} on {p4c.get_jupyter_bridge_url()}')
  if _PY4CYTOSCAPE_RUNNING_IN_COLAB:
    print('ADVICE: WHEN RUNNING UNDER COLAB, DO NOT RE-RUN THIS CELL WITHOUT MANUALLY EXECUTING Runtime | Factory Reset Runtime FROM THE COLAB MENU FIRST.')

# Caller must do this part: IPython.display.Javascript(_PY4CYTOSCAPE_BROWSER_CLIENT_JS) # Start browser client'
