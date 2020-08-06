echo When executing this, be sure pwd=/home/bdemchak/jupyter-bridge

sudo systemctl stop jupyter-bridge
sudo rm server/jupyter-bridge.log
sudo systemctl start jupyter-bridge
sudo systemctl status jupyter-bridge