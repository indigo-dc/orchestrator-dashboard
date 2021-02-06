from app import app, iam_blueprint, sla as sla, settings, utils, vault
from werkzeug.exceptions import Forbidden
from flask import json, render_template, request, redirect, url_for, flash, session, Markup
import requests, json
import yaml
import io, os, sys
from functools import wraps
from packaging import version

app.jinja_env.filters['tojson_pretty'] = utils.to_pretty_json

toscaTemplates = utils.loadToscaTemplates(settings.toscaDir)
toscaInfo = utils.extractToscaInfo(settings.toscaDir,settings.toscaParamsDir,toscaTemplates)

app.logger.debug("TOSCA INFO: " + json.dumps(toscaInfo))
app.logger.debug("EXTERNAL_LINKS: " + json.dumps(settings.external_links) )
app.logger.debug("ENABLE_ADVANCED_MENU: " + str(settings.enable_advanced_menu) )

@app.before_request
def before_request_checks():
    if 'external_links' not in session:
       session['external_links'] = settings.external_links
    if 'enable_advanced_menu' not in session:
       session['enable_advanced_menu'] = settings.enable_advanced_menu

def validate_configuration():
   if not settings.orchestratorConf.get('im_url'):
       app.logger.debug("Trying to (re)load config from Orchestrator: " + json.dumps(settings.orchestratorConf))
       access_token = iam_blueprint.session.token['access_token']
       configuration = utils.getOrchestratorConfiguration(settings.orchestratorUrl, access_token)
       settings.orchestratorConf = configuration

def authorized_with_valid_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not iam_blueprint.session.authorized or 'username' not in session:
           return redirect(url_for('login'))

        if iam_blueprint.session.token['expires_in'] < 20:
            app.logger.debug("Force refresh token")
            iam_blueprint.session.get('/userinfo')

        validate_configuration()

        return f(*args, **kwargs)

    return decorated_function

@app.route('/settings')
@authorized_with_valid_token
def show_settings():
    return render_template('settings.html', iam_url=settings.iamUrl, orchestrator_url=settings.orchestratorUrl, orchestrator_conf=settings.orchestratorConf)

@app.route('/login')
def login():
    session.clear()
    return render_template('home.html')

@app.route('/slas')
@authorized_with_valid_token
def getslas():

  slas={}

  try:
    access_token = iam_blueprint.session.token['access_token']
    slas = sla.get_slas(access_token, settings.orchestratorConf['slam_url'], settings.orchestratorConf['cmdb_url'])

  except Exception as e:
        flash("Error retrieving SLAs list: \n" + str(e), 'warning')

  return render_template('sla.html', slas=slas)


def check_template_access(allowed_groups, user_groups):

    #check intersection of user groups with user membership
    if (set(allowed_groups.split(','))&set(user_groups)) != set() or allowed_groups == '*':
        return True
    else:
        return False

@app.route('/')
def home():
    if not iam_blueprint.session.authorized:
        return redirect(url_for('login'))
    
    account_info = iam_blueprint.session.get("/userinfo")

    if account_info.ok:
        account_info_json = account_info.json()
        user_groups = account_info_json['groups']

        if settings.iamGroups:
            if not set(settings.iamGroups).issubset(user_groups):
                app.logger.debug("No match on group membership. User group membership: " + json.dumps(user_groups))
                message = Markup('You need to be a member of the following IAM groups: {0}. <br> Please, visit <a href="{1}">{1}</a> and apply for the requested membership.'.format(json.dumps(settings.iamGroups), settings.iamUrl))
                raise Forbidden(description=message)
            
        session['username'] = account_info_json['name']
        session['gravatar'] = utils.avatar(account_info_json['email'], 26)
        session['organisation_name'] = account_info_json['organisation_name']
        access_token = iam_blueprint.token['access_token']

        templates = { k:v for (k,v) in toscaInfo.items() if check_template_access(v.get("metadata").get("allowed_groups"),user_groups) }
        return render_template('portfolio.html', templates=templates)
        

@app.route('/deployments')
@authorized_with_valid_token
def showdeployments():

    access_token = iam_blueprint.session.token['access_token']

    headers = {'Authorization': 'bearer %s' % (access_token)}

    url = settings.orchestratorUrl +  "/deployments?createdBy=me&page=0&size=9999"
    response = requests.get(url, headers=headers)

    deployments = {}
    if not response.ok:
        flash("Error retrieving deployment list: \n" + response.text, 'warning')
    else:
        deployments = response.json()["content"]
        app.logger.debug("Deployments: " + str(deployments))
    return render_template('deployments.html', deployments=deployments)



@app.route('/template/<depid>')
@authorized_with_valid_token
def deptemplate(depid=None):

    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % (access_token)}

    url = settings.orchestratorUrl + "/deployments/" + depid + "/template"
    response = requests.get(url, headers=headers)

    if not response.ok:
      flash("Error getting template: " + response.text)
      return redirect(url_for('home'))

    template = response.text
    return render_template('deptemplate.html', template=template)
#

@app.route('/log/<physicalId>')
@authorized_with_valid_token
def deplog(physicalId=None):

    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'id = im; type = InfrastructureManager; token = %s;' % (access_token)}

    app.logger.debug("Configuration: " + json.dumps(settings.orchestratorConf))

    url = settings.orchestratorConf['im_url'] + "/infrastructures/" + physicalId + "/contmsg"
    response = requests.get(url, headers=headers, verify=False)

    if not response.ok:
      log="Not found"
    else:
      log = response.text
    return render_template('deplog.html', log=log)


@app.route('/delete/<depid>')
@authorized_with_valid_token
def depdel(depid=None):

    access_token = iam_blueprint.session.token['access_token']
    headers = {'Authorization': 'bearer %s' % (access_token)}
    url = settings.orchestratorUrl + "/deployments/" + depid
    response = requests.delete(url, headers=headers)
       
    if not response.ok:
        flash("Error deleting deployment: " + response.text);
  
    return redirect(url_for('showdeployments'))


@app.route('/configure')
@authorized_with_valid_token
def configure():

    access_token = iam_blueprint.session.token['access_token']

    selected_tosca = request.args['selected_tosca']

    slas = sla.get_slas(access_token, settings.orchestratorConf['slam_url'], settings.orchestratorConf['cmdb_url'], toscaInfo[selected_tosca]["deployment_type"])

    app.logger.debug("Template: " + json.dumps(toscaInfo[selected_tosca]))

    return render_template('createdep.html',
                           template=toscaInfo[selected_tosca],
                           selectedTemplate=selected_tosca,
                           slas=slas)


def add_sla_to_template(template, sla_id):
    # Add the placement policy

    if version.parse(utils.getOrchestratorVersion(settings.orchestratorUrl).split('-')[0]) >= version.parse("2.2.0"):
        toscaSlaPlacementType = "tosca.policies.indigo.SlaPlacement"
    else:
        toscaSlaPlacementType = "tosca.policies.Placement"

    template['topology_template']['policies'] = [
           {"deploy_on_specific_site": { "type": toscaSlaPlacementType, "properties": {"sla_id": sla_id}}}]

    app.logger.debug(yaml.dump(template, default_flow_style=False))

    return template
#        
# 
@app.route('/submit', methods=['POST'])
@authorized_with_valid_token
def createdep():

  access_token = iam_blueprint.session.token['access_token']

  app.logger.debug("Form data: " + json.dumps(request.form.to_dict()))

  with io.open( settings.toscaDir + request.args.get('template')) as stream:
      template = yaml.full_load(stream)

      form_data = request.form.to_dict()
     
      params={}
      if 'extra_opts.keepLastAttempt' in form_data:
         params['keepLastAttempt'] = 'true'
      else:
         params['keepLastAttempt'] = 'false'

      if form_data['extra_opts.schedtype'] == "man":
          template = add_sla_to_template(template, form_data['extra_opts.selectedSLA'])

      if 'extra_opts.providerTimeoutSet' in form_data:
          params['providerTimeoutMins'] = form_data['extra_opts.providerTimeout']

      inputs = { k:v for (k,v) in form_data.items() if not k.startswith("extra_opts.") }

      app.logger.debug("Parameters: " + json.dumps(inputs))

      payload = { "template" : yaml.dump(template,default_flow_style=False, sort_keys=False), "parameters": inputs }
      # set additional params
      payload.update(params)


  url = settings.orchestratorUrl +  "/deployments/"
  headers = {'Content-Type': 'application/json', 'Authorization': 'bearer %s' % (access_token)}
  response = requests.post(url, json=payload, headers=headers)

  if not response.ok:
     flash("Error submitting deployment: \n" + response.text)

  return redirect(url_for('showdeployments'))
 
@app.route('/manage_creds')
@authorized_with_valid_token
def manage_creds():
  slas={}

  try:
    access_token = iam_blueprint.session.token['access_token']
    slas = sla.get_slas(access_token, settings.orchestratorConf['slam_url'], settings.orchestratorConf['cmdb_url'])

  except Exception as e:
        flash("Error retrieving SLAs list: \n" + str(e), 'warning')

  return render_template('service_creds.html', slas=slas)



@app.route('/read_secret_from_vault')
@authorized_with_valid_token
def read_secret_from_vault():
    
    serviceid = request.args.get('service_id',None)
    servicetype = request.args.get('service_type',None)

    access_token = iam_blueprint.session.token['access_token']
    jwt_token=utils.exchange_token_with_audience(settings.iamUrl, app.config['IAM_CLIENT_ID'], app.config['IAM_CLIENT_SECRET'],access_token,settings.vault_audience)
    vault_client = vault.VaultClient(settings.orchestratorConf['vault_url'],jwt_token,settings.vault_role)
    path = "services_credential/" + serviceid
    secret = vault_client.read_service_creds( path )

    if secret:
        secret = secret.get('data')

    return render_template('modal_creds.html', mode="filled-form", service_creds=secret, service_type=servicetype)


@app.route('/write_secret_to_vault', methods=['GET', 'POST'])
@authorized_with_valid_token
def write_secret_to_vault():

    serviceid = request.args.get('service_id',"")
    servicetype = request.args.get('service_type',"")

    app.logger.debug("service_id={}".format(serviceid))

    if request.method == 'GET':
       return render_template('modal_creds.html', mode="empty-form", service_creds=None, service_type=servicetype, service_id=serviceid)
    else:    

       app.logger.debug("Form data: " + json.dumps(request.form.to_dict()))

       creds = request.form.to_dict()

       access_token = iam_blueprint.session.token['access_token']
   
       jwt_token=utils.exchange_token_with_audience(settings.iamUrl, app.config['IAM_CLIENT_ID'], app.config['IAM_CLIENT_SECRET'],access_token,settings.vault_audience)
       vault_client = vault.VaultClient(settings.orchestratorConf['vault_url'],jwt_token,settings.vault_role)
       path = "services_credential/" + serviceid
       secret = vault_client.write_service_creds( path, creds )

       flash("Credentials successfully written!", 'info')

       return redirect(url_for('manage_creds'))

@app.route('/delete_secret_from_vault')
@authorized_with_valid_token
def delete_secret_from_vault():

    serviceid = request.args.get('service_id',"")
    servicetype = request.args.get('service_type',"")

    access_token = iam_blueprint.session.token['access_token']

    jwt_token=utils.exchange_token_with_audience(settings.iamUrl, app.config['IAM_CLIENT_ID'], app.config['IAM_CLIENT_SECRET'],access_token,settings.vault_audience)
    vault_client = vault.VaultClient(settings.orchestratorConf['vault_url'],jwt_token,settings.vault_role)
    path = "services_credential/" + serviceid
    vault_client.delete_service_creds(path)

    flash("Credentials successfully deleted!", 'info')
    
    return redirect(url_for('manage_creds'))

@app.route('/get_monitoring_info')
@authorized_with_valid_token
def get_monitoring_info():
    
    provider = request.args.get('provider',None)
    serviceid = request.args.get('service_id',None)
    servicetype = request.args.get('service_type',None)

    access_token = iam_blueprint.session.token['access_token']

    headers = {'Authorization': 'bearer %s' % (access_token)}
    url = settings.orchestratorConf['monitoring_url'] + "/monitoring/adapters/zabbix/zones/indigo/types/infrastructure/groups/" + provider + "/hosts/" + serviceid
    response = requests.get(url, headers=headers)

    monitoring_data = {}

    if response.ok:
        try:
          monitoring_data = response.json()['result']['groups'][0]['paasMachines'][0]['services'][0]['paasMetrics']
        except Exception as e:
          app.logger.debug("Error getting monitoring data")

    return render_template('monitoring_metrics.html', monitoring_data=monitoring_data)

@app.route('/logout')
def logout():
   session.clear()
   iam_blueprint.session.get("/logout")
   return redirect(url_for('login'))
