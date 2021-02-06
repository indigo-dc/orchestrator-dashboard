import hvac
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import os
import ast, json

class VaultClient:
    def __init__(self, vault_url, jwt_token, role): 

        login_url = vault_url + '/v1/auth/jwt/login'
        
        data = '{ "jwt": "'+ jwt_token +  '", "role": "'+ role +  '" }'
        
        response = requests.post(login_url, data=data, verify=False)
        
        if not response.ok:
            raise Exception("Error getting Vault token: {} - {}".format(response.status_code, response.text) )
        
        deserialized_response = json.loads(response.text)
        
        self.vault_auth_token = deserialized_response["auth"]["client_token"]
        self.vault_entity_id = deserialized_response["auth"]["entity_id"]
        
        self.client = hvac.Client(url=vault_url,token=self.vault_auth_token)
        if not self.client.is_authenticated():
            raise Exception("Error authenticating against Vault with token: {}".format(self.vault_auth_token))

    def read_service_creds(self, path):
        
        vault_secret_path = "data/"+ self.vault_entity_id + "/" + path
        secret = None

        try:
            secret = self.client.secrets.kv.v1.read_secret(path=vault_secret_path, mount_point="secret")
        except hvac.exceptions.InvalidPath as e:
            secret = None
        return secret

    def write_service_creds(self, path, creds):

        vault_secret_path = "data/"+ self.vault_entity_id + "/" + path

        self.client.secrets.kv.v1.create_or_update_secret(path=vault_secret_path, mount_point="secret", secret=creds)

    def delete_service_creds(self, path):

        vault_secret_path = "data/"+ self.vault_entity_id + "/" + path

        self.client.secrets.kv.v1.delete_secret(path=vault_secret_path, mount_point="secret")
