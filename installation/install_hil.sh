# Install HIL

# Disable SELinux
sudo setenforce 0

# Add a hil system user named hil
sudo useradd --system hil -d /var/lib/hil -m -r

# install hil
cd ../
sudo pip install .

# copy hil config file and create a symbolic link
sudo cp examples/hil.cfg /etc/hil.cfg
sudo chown hil:hil /etc/hil.cfg
sudo ln -s -f /etc/hil.cfg /var/lib/hil

# copy the hil wsgi file
sudo mkdir -p /var/www/hil && sudo cp hil.wsgi /var/www/hil/

# copy the hil_network service and the create_bridges service
sudo cp scripts/hil_network.service /usr/lib/systemd/system
sudo cp scripts/create_bridges.service /usr/lib/systemd/system
sudo cp installation/wsgi.conf /etc/httpd/conf.d/ --force

# enable the services, but don't start them yet.
sudo systemctl daemon-reload
sudo systemctl enable hil_network.service
sudo systemctl enable create_bridges.service
sudo systemctl enable httpd

# start httpd though
sudo systemctl restart httpd
