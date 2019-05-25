from app import app, iam_blueprint, iam_base_url
from flask import json, current_app, render_template, request, redirect, url_for, flash, session
import requests, json
import yaml
import io, os, sys
from fnmatch import fnmatch
from hashlib import md5


def to_pretty_json(value):
    return json.dumps(value, sort_keys=True,
                      indent=4, separators=(',', ': '))

app.jinja_env.filters['tojson_pretty'] = to_pretty_json


def avatar(email, size):
  digest = md5(email.lower().encode('utf-8')).hexdigest()
  return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)


toscaDir=app.config.get('TOSCA_TEMPLATES_DIR') + "/"
toscaTemplates = []
for path, subdirs, files in os.walk(toscaDir):
   for name in files:
        if fnmatch(name, "*.yml") or fnmatch(name, "*.yaml"):
            # skip hidden files
            if name[0] != '.': 
               toscaTemplates.append( os.path.relpath(os.path.join(path, name), toscaDir ))

orchestratorUrl = app.config.get('ORCHESTRATOR_URL')
slamUrl = app.config.get('SLAM_URL')
cmdbUrl = app.config.get('CMDB_URL')

@app.route('/settings')
def show_settings():
    if not iam_blueprint.session.authorized:
       return redirect(url_for('login'))
    return render_template('settings.html', orchestrator_url=orchestratorUrl, iam_url=iam_base_url)

@app.route('/login')
def login():
    session.clear()
    return render_template('home.html')


def get_service_type(access_token, service_id):
    headers = {'Authorization': 'bearer %s' % (access_token)}
    url = cmdbUrl + "/service/id/" + service_id
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    app.logger.info(json.dumps(response.json()['data']['service_type']))

    service_type=response.json()['data']['service_type']

    if 'properties' in response.json()['data']:
        if 'gpu_support' in response.json()['data']['properties']:
            service_type = service_type + " (gpu_support: " + str(response.json()['data']['properties']['gpu_support']) + ")"

    return service_type

def get_slas(access_token):

    headers = {'Authorization': 'bearer %s' % (access_token)}

    url = slamUrl + "/rest/slam/preferences/" + session['organisation_name']
    response = requests.get(url, headers=headers, timeout=20)
    app.logger.info("SLA response status: " + str(response.status_code))

    response.raise_for_status()
    app.logger.info("SLA response: " + json.dumps(response.json()))
    slas = response.json()['sla']

    for i in range(len(slas)):
       service_type=get_service_type(access_token,slas[i]['services'][0]['service_id'])
       slas[i]['service_type']=service_type

    return slas

@app.route('/slas')
def getslas():

  if not iam_blueprint.session.authorized:
     return redirect(url_for('login'))

  slas={}

  try:
    access_token = iam_blueprint.token['access_token']
    slas = get_slas(access_token)

  except Exception as e:
        flash("Error retrieving SLAs list: \n" + str(e), 'warning')
        return redirect(url_for('home'))

  return render_template('sla.html', slas=slas)


@app.route('/dashboard/<page>')
@app.route('/<page>')
@app.route('/')
def home(page=0):

  if not iam_blueprint.session.authorized:
     return redirect(url_for('login'))
  try:
    account_info=iam_blueprint.session.get("/userinfo")

    if account_info.ok:
        account_info_json = account_info.json()
        session['username']  = account_info_json['name']
        session['gravatar'] = avatar(account_info_json['email'], 26)
        session['organisation_name']=account_info_json['organisation_name']
        access_token = iam_blueprint.token['access_token']

        headers = {'Authorization': 'bearer %s' % (access_token)}

        url = orchestratorUrl +  "/deployments?createdBy=me&page=" + str(page)
        response = requests.get(url, headers=headers)

        deployments = {}
        if not response.ok:
            flash("Error retrieving deployment list: \n" + response.text, 'warning')
        else:
            deployments = response.json()["content"]
            pages=response.json()['page']['totalPages']
            app.logger.debug(pages)
        return render_template('deployments.html', deployments=deployments, tot_pages=pages, current_page=page)
  except Exception:
      app.logger.info("error")
      return redirect(url_for('logout'))


@app.route('/template/<depid>')
def deptemplate(depid=None):

    if not iam_blueprint.session.authorized:
       return redirect(url_for('login'))

    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % (access_token)}

    url = orchestratorUrl + "/deployments/" + depid + "/template"
    response = requests.get(url, headers=headers)

    if not response.ok:
      flash("Error getting template: " + response.text)
      return redirect(url_for('home'))

    template = response.text
    return render_template('deptemplate.html', template=template)
#
@app.route('/delete/<depid>')
def depdel(depid=None):

    if not iam_blueprint.session.authorized:
       return redirect(url_for('login'))

    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % (access_token)}
    url = orchestratorUrl + "/deployments/" + depid
    response = requests.delete(url, headers=headers)
       
    if not response.ok:
        flash("Error deleting deployment: " + response.text);
  
    return redirect(url_for('home'))
#
@app.route('/create', methods=['GET', 'POST'])
def depcreate():
     if not iam_blueprint.session.authorized:
        return redirect(url_for('login'))

     access_token = iam_blueprint.session.token['access_token']

     if request.method == 'GET':
        return render_template('createdep.html', templates=toscaTemplates, inputs={})
     else:
        selected_tosca = request.form.get('tosca_template')
        
        with io.open( toscaDir + selected_tosca) as stream:
           template = yaml.load(stream)
           if 'topology_template' not in template:
             flash("Error reading template \"" + selected_tosca + "\": syntax is not correct. Please select another template.");
             return redirect(url_for('depcreate'))

           inputs={}
           if 'inputs' in template['topology_template']:
              inputs = template['topology_template']['inputs']
           
           description = "N/A"
           if 'description' in template:
              description = template['description']

           slas = get_slas(access_token)
           return render_template('createdep.html', templates=toscaTemplates, selectedTemplate=selected_tosca, description=description,  inputs=inputs, slas=slas)

def add_sla_to_template(template, sla_id):
    # Add the placement policy

    nodes=template['topology_template']['node_templates']
    compute_nodes = []
    for key, dict in nodes.items():
        node_type=dict["type"]
        if node_type == "tosca.nodes.indigo.Compute" or node_type == "tosca.nodes.indigo.Container.Application.Docker.Chronos" :
            compute_nodes.append(key)
    template['topology_template']['policies']=[{ "deploy_on_specific_site": { "type": "tosca.policies.Placement", "properties": { "sla_id": sla_id }, "targets": compute_nodes  } }]
    app.logger.info(yaml.dump(template,default_flow_style=False))
    return template
#        
# 
@app.route('/submit', methods=['POST'])
def createdep():

  if not iam_blueprint.session.authorized:
     return redirect(url_for('login'))

  access_token = iam_blueprint.session.token['access_token']

  try:
     with io.open( toscaDir + request.args.get('template')) as stream:
         template = yaml.load(stream)
         if 'selectSla' in request.form.to_dict():
             template = add_sla_to_template(template, request.form.get('selectedSLA'))

         payload = { "template" : yaml.dump(template,default_flow_style=False), "parameters": request.form.to_dict() }

     body= json.dumps(payload)

     url = orchestratorUrl +  "/deployments/"
     headers = {'Content-Type': 'application/json', 'Authorization': 'bearer %s' % (access_token)}
     response = requests.post(url, data=body, headers=headers)

     if not response.ok:
               flash("Error submitting deployment: \n" + response.text)

     return redirect(url_for('home'))
 
  except Exception as e:
     flash("Error submitting deployment:" + str(e) + ". Please retry")
     return redirect(url_for('home'))


@app.route('/logout')
def logout():
   session.clear()
   iam_blueprint.session.get("/logout")
#   del iam_blueprint.session.token
   return redirect(url_for('login'))


