import json, yaml, requests, os, io, ast
from fnmatch import fnmatch
from hashlib import md5
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

def to_pretty_json(value):
    return json.dumps(value, sort_keys=True,
                      indent=4, separators=(',', ': '))

def avatar(email, size):
  digest = md5(email.lower().encode('utf-8')).hexdigest()
  return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)


def getOrchestratorVersion(orchestrator_url):
    url = orchestrator_url +  "/info"
    response = requests.get(url)

    return response.json()['build']['version']


def getOrchestratorConfiguration(orchestrator_url, access_token):
    
    headers = {'Authorization': 'bearer %s' % (access_token)}

    url = orchestrator_url +  "/configuration"
    response = requests.get(url, headers=headers)

    configuration = {}
    if response.ok:
        configuration = response.json()

    return configuration

def loadToscaTemplates(directory):

   toscaTemplates = []
   for path, subdirs, files in os.walk(directory):
      for name in sorted(files):
           if fnmatch(name, "*.yml") or fnmatch(name, "*.yaml"):
               # skip hidden files
               if name[0] != '.':
                  toscaTemplates.append( os.path.relpath(os.path.join(path, name), directory ))

   return toscaTemplates


def getdeploymenttype(nodes):
    deployment_type = ""
    for (j, u) in nodes.items():
        if deployment_type == "":
            for (k, v) in u.items():
                if k == "type" and v == "tosca.nodes.indigo.Compute":
                    deployment_type = "CLOUD"
                    break
                if k == "type" and v == "tosca.nodes.indigo.Container.Application.Docker.Marathon":
                    deployment_type = "MARATHON"
                    break
                if k == "type" and v == "tosca.nodes.indigo.Container.Application.Docker.Chronos":
                    deployment_type = "CHRONOS"
                    break
                if k == "type" and v == "tosca.nodes.indigo.Qcg.Job":
                    deployment_type = "QCG"
                    break
    return deployment_type

def extractToscaInfo(toscaDir, tosca_pars_dir, toscaTemplates):
    toscaInfo = {}
    for tosca in toscaTemplates:
        with io.open( toscaDir + tosca) as stream:
           template = yaml.full_load(stream)
    
           toscaInfo[tosca] = {
                                "valid": True,
                                "description": "TOSCA Template",
                                "metadata": {
                                    "icon": "https://cdn4.iconfinder.com/data/icons/mosaicon-04/512/websettings-512.png",
                                    "allowed_groups": '*'
                                },
                                "enable_config_form": False,
                                "inputs": {},
                                "tabs": {}
                              }
    
           if 'topology_template' not in template:
               toscaInfo[tosca]["valid"] = False
    
           else:
    
                if 'description' in template:
                    toscaInfo[tosca]["description"] = template['description']
    
                if 'metadata' in template and template['metadata'] is not None:
                   for k,v in template['metadata'].items():
                       toscaInfo[tosca]["metadata"][k] = v
    
                if 'inputs' in template['topology_template']:
                   toscaInfo[tosca]['inputs'] = template['topology_template']['inputs']

                if 'node_templates' in template['topology_template']:
                   toscaInfo[tosca]['deployment_type'] = getdeploymenttype(template['topology_template']['node_templates'])   
    
                ## add parameters code here
                tabs = {}
                if tosca_pars_dir:
                    tosca_pars_path = tosca_pars_dir + "/"  # this has to be reassigned here because is local.
                    for fpath, subs, fnames in os.walk(tosca_pars_path):
                        for fname in fnames:
                            if fnmatch(fname, os.path.splitext(tosca)[0] + '.parameters.yml') or \
                                    fnmatch(fname, os.path.splitext(tosca)[0] + '.parameters.yaml'):
                                # skip hidden files
                                if fname[0] != '.':
                                    tosca_pars_file = os.path.join(fpath, fname)
                                    with io.open(tosca_pars_file) as pars_file:
                                        toscaInfo[tosca]['enable_config_form'] = True
                                        pars_data = yaml.full_load(pars_file)
                                        toscaInfo[tosca]['inputs'] = pars_data["inputs"]
                                        if "tabs" in pars_data:
                                            toscaInfo[tosca]['tabs'] = pars_data["tabs"]

    return toscaInfo

def exchange_token_with_audience(iam_url, client_id, client_secret, iam_token, audience):

    payload_string = '{ "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange", "audience": "'+audience+'", "subject_token": "'+iam_token+'", "scope": "openid profile" }'
    
    # Convert string payload to dictionary
    payload =  ast.literal_eval(payload_string)
    
    iam_response = requests.post(iam_url + "/token", data=payload, auth=(client_id, client_secret), verify=False)
    
    if not iam_response.ok:
        raise Exception("Error exchanging token: {} - {}".format(iam_response.status_code, iam_response.text) )
    
    deserialized_iam_response = json.loads(iam_response.text)
    
    return deserialized_iam_response['access_token']
