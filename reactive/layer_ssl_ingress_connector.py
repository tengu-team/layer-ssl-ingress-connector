import os
import json
import yaml
import subprocess as sp
import shutil
import hashlib
from charmhelpers.core import unitdata, hookenv, host
from charmhelpers.core.templating import render
from charmhelpers.core.hookenv import status_set, config, application_name, log
from charms.reactive import when, when_not, when_not, set_flag, clear_flag, when_any
from charms.reactive.relations import endpoint_from_flag
from charms.layer.resourcefactory import ResourceFactory
from charms.layer.k8shelpers import (
    delete_resources_by_label,
    get_label_values_per_deployer,
    add_label_to_resource,
    get_worker_node_ips,
    resource_owner,
    get_resource_by_file,
)

config = hookenv.config()
deployer = os.environ['JUJU_UNIT_NAME'].split('/')[0]


@when('deployer.installed')
@when_not('ingress.installed')
def install_ingress_service():
    req_uuid = get_uuid()
    context = {'namespace': get_ingress_namespace()}
    resource = render('ingress_service.yaml', None, context)
    requests = {req_uuid: {
                        'model_uuid': os.environ['JUJU_MODEL_UUID'],
                        'juju_unit': deployer,
                        'requests': [yaml.load(resource)]
                    }}
    configure_namespace()
    unitdata.kv().set('used_apps', list(requests.keys()))
    clean_deployer_config(['resources'])
    send_requests(requests)
    set_flag('ingress.installed')


########################################################################
# Relations
########################################################################
@when_not('endpoint.ssl-termination.available')
@when('ingress.installed')
def missing_ssl_termination_relation():
    status_set('blocked', 'Waiting for ssl-termination-proxy relation')


@when_any('config.changed.fqdns',
          'config.changed.credentials')
@when('ingress.installed')
def fqdns_changed():
    clear_flag('client.cert-requested')
    clear_flag('client.cert-created')


########################################################################
# Configure certificateS
########################################################################
@when('ingress.installed',
      'endpoint.ssl-termination.available')
@when_not('client.cert-requested')
def create_cert_request():
    if not config.get('fqdns'):
        status_set('blocked', 'Waiting for fqdns config')
        return
    ssl_termination = endpoint_from_flag('endpoint.ssl-termination.available')
    workers = get_worker_node_ips()
    if not workers:
        return
    upstreams = []
    ingress_nodeport = get_ingress_nodeport()
    for worker in workers:
        host = [{'hostname': worker,
                'private-address': worker,
                'port': ingress_nodeport}]
        upstreams.extend(host)
    print(upstreams)
    ssl_termination.send_cert_info({
        'fqdn': config.get('fqdns').rstrip().split(),
        'contact-email': config.get('contact-email', ''),
        'credentials': config.get('credentials', ''),
        'upstreams': upstreams,
    })
    status_set('waiting', 'Waiting for proxy to register certificate')
    set_flag('client.cert-requested')


@when('endpoint.ssl-termination.update')
@when_not('client.cert-created')
def check_cert_created():
    ssl_termination = endpoint_from_flag('endpoint.ssl-termination.update')
    status = ssl_termination.get_status()

    # Only one fqdn will be returned for shared certs.
    # If any fqdn match, the cert has been created.
    match_fqdn = config.get('fqdns').rstrip().split()
    for unit_status in status:
        for fqdn in unit_status['status']:
            if fqdn in match_fqdn:
                status_set('active', 'Ready')
                set_flag('client.cert-created')
                clear_flag('endpoint.ssl-termination.update')


########################################################################
#    K8s helper functions
########################################################################
def send_requests(requests):
    error_states = {}
    for uuid in requests:
        resource_id = 0
        for resource in requests[uuid]['requests']:
            # Check if there is a naming conflict in the namespace
            if resource_name_duplicate(resource, uuid) :
                error_states[uuid] = {'error' : 'Duplicate name for resource: '
                                                + resource['metadata']['name']}
                log('Duplicate name for resource: ' + resource['metadata']['name'])
                continue
            prepared_request = {
                'uuid' : uuid,
                'resource' : resource,
                'namespace' : unitdata.kv().get('namespace').rstrip(),
                'unique_id' : resource_id,
                'model_uuid' : requests[uuid]['model_uuid'],
                'juju_unit' : requests[uuid]['juju_unit'],
            }
            resource_id += 1
            pre_resource = ResourceFactory.create_resource('preparedresource', prepared_request)
            pre_resource.write_resource_file()
            if not pre_resource.create_resource() :
                error_states[uuid] = {'error' : 'Could not create requested resources.'}
    # Save the error states so update_status_info handler can report them
    unitdata.kv().set('error-states', error_states)


def configure_namespace():
    namespace = ResourceFactory.create_resource('namespace', {'name': unitdata.kv().get('namespace').rstrip(),
                                                              'deployer': deployer})
    namespace.write_resource_file()
    namespace.create_resource()



def get_uuid():
    k8s_uuid = unitdata.kv().get('k8s_uuid', None)
    if not k8s_uuid:
        juju_model = os.environ['JUJU_MODEL_UUID']
        juju_app_name = os.environ['JUJU_UNIT_NAME'].split('/')[0]
        unique_name = juju_model + juju_app_name
        k8s_uuid = hashlib.md5(unique_name.encode('utf-8')).hexdigest()
        unitdata.kv().set('k8s_uuid', k8s_uuid)
    return k8s_uuid


def clean_deployer_config(resources):
    if resources is None:
        return
    for resource in resources :
        path = unitdata.kv().get('deployer_path') + '/' + resource
        shutil.rmtree(path)
        os.mkdir(path)


def resource_name_duplicate(resource, app):
    print(resource)
    owner = resource_owner(config.get('namespace', 'default'),
                           resource['metadata']['name'],
                           unitdata.kv().get('juju_app_selector'))
    if owner and owner != app:
        return True
    return False


def get_ingress_namespace():
    cmd = ['kubectl', 'get', 'namespaces', '-o', 'json']
    output = sp.check_output(cmd).decode('utf-8')
    result = json.loads(output)
    namespaces = [x['metadata']['name']  for x in result['items'] if 'ingress' in  x['metadata']['name']]
    if len(namespaces) > 0:
        unitdata.kv().set('namespace',namespaces[0])
        return namespaces[0]
    return None


def get_ingress_nodeport():
    cmd = ['kubectl', 'get', 'service', 'ingress-nginx-kubernetes-worker', '-n', 'ingress-nginx-kubernetes-worker', '-o', 'json']
    output = sp.check_output(cmd).decode('utf-8')
    result = json.loads(output)
    nodeport = [x['nodePort'] for x in result['spec']['ports'] if x['port'] == 80]
    if len(nodeport) > 0:
        unitdata.kv().set('nodeport',nodeport[0])
        return nodeport[0]
    return None
