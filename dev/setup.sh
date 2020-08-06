echo When executing this, be sure pwd=/home/bdemchak/jupyter-bridge

echo Set up NGINX configuration for web page
sudo cp server/config/jupyter-bridge.cytoscape.org /etc/nginx/sites-available/jupyter-bridge.cytoscape.org
sudo ln -s /etc/nginx/sites-available/jupyter-bridge.cytoscape.org /etc/nginx/sites-enabled/

echo Make sure this exists: /etc/letsencrypt/options-ssl-nginx.conf;
echo Make sure this exists: /etc/letsencrypt/ssl-dhparams.pem;

echo Manually install your fullchain.pem and privkey.pem into /etc/letsencrypt/live/jupyter-bridge.cytoscape.org

sudo cp server/config/jupyter-bridge.service /etc/systemd/system/
sudo systemctl start jupyter-bridge
sudo systemctl enable jupyter-bridge
sudo systemctl status jupyter-bridge
