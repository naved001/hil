#!/usr/bin/env bash

# Setup configuration
cp ci/testsuite.cfg.$DB testsuite.cfg
sudo cp ci/apache/hil.cfg.$DB /etc/hil.cfg
sudo chown travis:travis /etc/hil.cfg

# Address #577 via
# https://stackoverflow.com/questions/2192323/what-is-the-python-egg-cache-python-egg-cache
mkdir -p ~/.python-eggs
chmod go-w ~/.python-eggs # Eliminate "writable by group/others" warnings

# Install HIL, incl. test dependencies
pip install .[tests]
