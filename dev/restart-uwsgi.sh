echo When executing this, be sure pwd=/home/bdemchak/
sudo systemctl stop jupyter-bridge
sudo rm jupyter-bridge/server/jupyter-bridge.log
sudo rm jupyter-bridge/server/uwsgi.jupyter-bridge.log
sudo systemctl start jupyter-bridge
sudo systemctl status jupyter-bridge