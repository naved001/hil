# This installs and configures postgres for HIL

sudo yum install postgresql-server postgresql-contrib -y
sudo postgresql-setup initdb

sudo sed -i 's|ident|md5|g' /var/lib/pgsql/data/pg_hba.conf

sudo systemctl restart postgresql
sudo systemctl enable postgresql

sudo -u postgres createuser -r -d -P hil

sudo -u hil createdb hil

