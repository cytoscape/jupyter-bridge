echo When executing this, be sure pwd=/home/bdemchak

echo see here for full nginx process from scratch: https://www.digitalocean.com/community/tutorials/how-to-install-nginx-on-ubuntu-18-04#:~:text=%20How%20To%20Install%20Nginx%20on%20Ubuntu%2018.04,of%20the%20installation%20process%2C%20Ubuntu%2018.04...%20More%20

echo Set up NGINX configuration for web page
sudo cp jupyter-bridge/server/config/jupyter-bridge.cytoscape.org /etc/nginx/sites-available/jupyter-bridge.cytoscape.org
sudo ln -s /etc/nginx/sites-available/jupyter-bridge.cytoscape.org /etc/nginx/sites-enabled/

echo Make sure this exists: /etc/letsencrypt/options-ssl-nginx.conf;
echo Make sure this exists: /etc/letsencrypt/ssl-dhparams.pem;

echo Manually install your fullchain.pem and privkey.pem into /etc/letsencrypt/live/jupyter-bridge.cytoscape.org

echo Install all the python components for building ... be sure pwd=/home/bdemchak
sudo apt install python3-pip python3-dev build-essential libssl-dev libffi-dev python3-setuptools
pip3 install virtualenv
python3 -m virtualenv jupyter-bridge-env
source jupyter-bridge-env/bin/activate
pip install wheel
pip install uwsgi flask redis requests
deactivate

echo see here for wsgi process: https://medium.com/swlh/deploy-flask-applications-with-uwsgi-and-nginx-on-ubuntu-18-04-2a47f378c3d2

sudo cp jupyter-bridge/server/config/jupyter-bridge.service /etc/systemd/system/
sudo systemctl start jupyter-bridge
sudo systemctl enable jupyter-bridge
sudo systemctl status jupyter-bridge
