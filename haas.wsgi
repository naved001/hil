#!/usr/bin/env python
from haas import api, config, server, migrations
config.setup('/etc/haas.cfg')
server.init()
migrations.check_db_schema()
from haas.rest import app as application  # noqa

# `api` is imported for the side-effect of registering the api functions.
# silence a pylint error about an unused import:
api

# ...and the app is imported because this is a wsgi script, and its job
# is to define `application`. Again, silence the error:
application
