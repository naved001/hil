#!/usr/bin/env sh
set -ex
export PATH=/usr/local/go/bin:$PATH
which go
go version
exit 2
py.test --cov=hil --cov-append tests/integration/migrate_ipmi_info.py
