# orchestrator-dashboard
INDIGO PaaS Orchestrator - Simple Graphical UI

Functionalities:
- IAM authentication
- Display user's deployments
- Display deployment details and template
- Delete deployment
- Create new deployment

The orchestrator-dashboard is a Python application built with the [Flask](http://flask.pocoo.org/) microframework; [Flask-Dance](https://flask-dance.readthedocs.io/en/latest/) is used for Openid-Connect/OAuth2 integration.


The docker image uses [Gunicorn](https://gunicorn.org/) as WSGI HTTP server to serve the Flask Application.

# How to deploy the dashboard

Register a client in IAM with the following properties:

- redirect uri: `https://<DASHBOARD_HOST>:<PORT>/login/iam/authorized`
- scopes: 'openid', 'email', 'profile', 'offline_access'
- introspection endpoint enabled

Create the `config.json` file (see the [example](app/config-sample.json)):

````
{
    "IAM_CLIENT_ID": "*****",
    "IAM_CLIENT_SECRET": "*****",
    "IAM_BASE_URL": "https://iam-test.indigo-datacloud.eu",
    "ORCHESTRATOR_URL": "https://indigo-paas.cloud.ba.infn.it/orchestrator",
    "TOSCA_TEMPLATES_DIR": "/opt/tosca-templates"
}
````
Clone the tosca-templates repository to get a set of tosca templates that the dashboard will load, e.g.:
````
git clone https://github.com/indigo-dc/tosca-templates -b stable/v3.0
````

You need to run the Orchestrator dashboard on HTTPS (otherwise you will get an error); you can choose between
- enabling the HTTPS support
- using an HTTPS proxy

Details are provided in the next paragraphs.

### Enabling HTTPS

You would need to provide
- a pair certificate/key that the container will read from the container paths `/certs/cert.pem` and `/certs/key.pem`;
- the environment variable `ENABLE_HTTPS` set to `True`
 

Run the docker container:
```
docker run -d -p 443:5001 --name='orchestrator-dashboard' \
           -e ENABLE_HTTPS=True \
           -v $PWD/cert.pem:/certs/cert.pem \
           -v $PWD/key.pem:/certs/key.pem \
           -v $PWD/config.json:/app/app/config.json \
           -v $PWD/tosca-templates:/opt/tosca-templates \
           marica/orchestrator-dashboard:latest
```
Access the dashboard at `https://<DASHBOARD_HOST>/`

### Using an HTTPS Proxy 

Example of configuration for nginx:
```
server {
      listen         80;
      server_name    YOUR_SERVER_NAME;
      return         301 https://$server_name$request_uri;
}

server {
  listen        443 ssl;
  server_name   YOUR_SERVER_NAME;
  access_log    /var/log/nginx/proxy-paas.access.log  combined;

  ssl on;
  ssl_protocols TLSv1 TLSv1.1 TLSv1.2;
  ssl_certificate           /etc/nginx/cert.pem;
  ssl_certificate_key       /etc/nginx/key.pem;
  ssl_trusted_certificate   /etc/nginx/trusted_ca_cert.pem;

  location / {
                # Pass the request to Gunicorn
                proxy_pass http://127.0.0.1:5001/;

                proxy_set_header        X-Real-IP $remote_addr;
                proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
                proxy_set_header        X-Forwarded-Proto https;
                proxy_set_header        Host $http_host;
                proxy_redirect          http:// https://;
                proxy_buffering         off;
  }

}
```

Run the docker container:

```
docker run -d -p 5001:5001 --name='orchestrator-dashboard' \
           -v $PWD/config.json:/app/app/config.json \
           -v $PWD/tosca-templates:/opt/tosca-templates \
           marica/orchestrator-dashboard:latest
```
:warning: Remember to update the redirect uri in the IAM client to `https://<PROXY_HOST>/login/iam/authorized`

Access the dashboard at `https://<PROXY_HOST>/`

### Performance tuning

You can change the number of gunicorn worker processes using the environment variable WORKERS.
E.g. if you want to use 2 workers, launch the container with the option `-e WORKERS=2`
Check the [documentation](http://docs.gunicorn.org/en/stable/design.html#how-many-workers) for ideas on tuning this parameter.

## How to build the docker image

```
git clone https://github.com/maricaantonacci/orchestrator-dashboard.git
cd orchestrator-dashboard
docker build -f docker/Dockerfile -t orchestrator-dashboard .
```

## How to setup a development environment

```
git clone https://github.com/maricaantonacci/orchestrator-dashboard.git
cd orchestrator-dashboard
python3 -m venv venv
source venv/source/activate
pip install -r requirements.txt
```

Start the dashboard app:
```
FLASK_app=orchdashboard flask run --host=0.0.0.0 --cert cert.pem --key privkey.pem --port 443
```


