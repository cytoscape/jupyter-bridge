import IPython

# If Colab, module is installed at system level. If Notebook, module is in user-space
RunningInCOLAB = 'google.colab' in str(get_ipython())
ModuleSpace = '' if RunningInCOLAB else '--user'
    
# Install py4cytoscape module into python space
get_ipython().run_line_magic('run', '-m pip uninstall -y py4cytoscape')
get_ipython().run_line_magic('run', '-m pip install ' + ModuleSpace + ' py4cytoscape')
import py4cytoscape as p4c

# Start the Jupyter-Bridge to enable communication with Cytoscape on workstation
print(f'Loading Javascript client ... {p4c.get_browser_client_channel()} on {p4c.get_jupyter_bridge_url()}')
browser_client_js = p4c.get_browser_client_js(True)
IPython.display.Javascript(browser_client_js) # Start browser client
