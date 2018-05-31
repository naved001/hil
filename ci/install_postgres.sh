#!/usr/bin/env bash

set -ex

# Skip if we are in the sqlite build
if [ $DB = sqlite ]; then
    exit 0
fi

# Stop and remove all previous postgres versions
sudo service postgresql stop

 # Install postgresql 10 manually because travis doesn't have it right now
echo "deb http://apt.postgresql.org/pub/repos/apt/ trusty-pgdg main" > pgdg.list
sudo mv pgdg.list /etc/apt/sources.list.d/
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
sudo apt-get update
sudo apt-get install postgresql -y

# Optimize Postgres:
# these changes optimize postgres. They are fine for testing, but not suitable
# for production.
# See https://www.postgresql.org/docs/current/static/non-durability.html
echo "fsync = off
synchronous_commit = off
full_page_writes = off
checkpoint_timeout = 30min
port = 5433
"| sudo tee --append /etc/postgresql/10/main/postgresql.conf

sudo service postgresql stop
sudo service postgresql start 10

# Initial setup for postgres that is done by travis, but we are doing
# it manually here
sudo -u postgres psql -p 5433 -c "ALTER USER postgres WITH ENCRYPTED PASSWORD 'hello';"
sudo -u postgres createdb hil_tests -p 5433
sudo -u postgres createdb hil -p 5433

# Setup postgres for our own use
sudo apt-get install -y python-psycopg2
