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

@app.route('/settings')
def show_settings():
    if not iam_blueprint.session.authorized:
       return redirect(url_for('login'))
    return render_template('settings.html', orchestrator_url=orchestratorUrl, iam_url=iam_base_url)

@app.route('/login')
def login():
    session.clear()
    return render_template('home.html')

@app.route('/dashboard/<page>')
@app.route('/<page>')
@app.route('/')
def home(page=0):

    if not iam_blueprint.session.authorized:
       return redirect(url_for('login'))
    
    account_info=iam_blueprint.session.get("/userinfo")

    if account_info.ok:
        account_info_json = account_info.json()
        session['username']  = account_info_json['name']
        session['gravatar'] = avatar(account_info_json['email'], 26)
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
           return render_template('createdep.html', templates=toscaTemplates, selectedTemplate=selected_tosca, description=description,  inputs=inputs)
#        
# 
@app.route('/submit', methods=['POST'])
def createdep():

  if not iam_blueprint.session.authorized:
     return redirect(url_for('login'))

  access_token = iam_blueprint.session.token['access_token']


  try:
     with io.open( toscaDir + request.args.get('template')) as stream:   
        payload = { "template" : stream.read(), "parameters": request.form.to_dict() }
      
     body= json.dumps(payload)

     url = orchestratorUrl +  "/deployments/"
     headers = {'Content-Type': 'application/json', 'Authorization': 'bearer %s' % (access_token)}
     response = requests.post(url, data=body, headers=headers)

     if not response.ok:
               flash("Error submitting deployment: \n" + response.text)
    
     return redirect(url_for('home'))
  except Exception as e:
     app.logger.error("Error submitting deployment:" + str(e))
     return redirect(url_for('home'))


@app.route('/logout')
def logout():
   session.clear()
   iam_blueprint.session.get("/logout")
#   del iam_blueprint.session.token
   return redirect(url_for('login'))

