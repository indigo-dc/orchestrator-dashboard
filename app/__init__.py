# Copyright (c) Istituto Nazionale di Fisica Nucleare (INFN). 2019-2020
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import Flask
from werkzeug.contrib.fixers import ProxyFix
from flask_dance.consumer import OAuth2ConsumerBlueprint
import logging

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key="30bb7cf2-1fef-4d26-83f0-8096b6dcc7a3"
app.config.from_json('config.json')

loglevel = app.config.get("LOG_LEVEL") if app.config.get("LOG_LEVEL") else "INFO"

numeric_level = getattr(logging, loglevel.upper(), None)
if not isinstance(numeric_level, int):
    raise ValueError('Invalid log level: %s' % loglevel)

logging.basicConfig(level=numeric_level)

iam_base_url=app.config['IAM_BASE_URL']
iam_token_url=iam_base_url + '/token'
iam_refresh_url=iam_base_url + '/token'
iam_authorization_url=iam_base_url + '/authorize'

iam_blueprint = OAuth2ConsumerBlueprint(
    "iam", __name__,
    client_id=app.config['IAM_CLIENT_ID'],
    client_secret=app.config['IAM_CLIENT_SECRET'],
    scope='openid email profile offline_access',
    base_url=iam_base_url,
    token_url=iam_token_url,
    auto_refresh_url=iam_refresh_url,
    authorization_url=iam_authorization_url,
    redirect_to='home'
)
app.register_blueprint(iam_blueprint, url_prefix="/login")

from app import routes, errors

if __name__ == "__main__":
    app.run(host='0.0.0.0')

