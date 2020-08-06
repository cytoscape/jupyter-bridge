export PYTHONPATH=..
source jupyter-bridge-env/bin/activate
cd jupyter-bridge/server
python3 -m unittest tests/test_jupyter_bridge.py
deactivate
cd ~