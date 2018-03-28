#!/usr/bin/env sh
set -ex
export PATH=$PATH:/usr/local/go/bin
py.test --cov=hil --cov-append tests/integration/migrate_ipmi_info.py
