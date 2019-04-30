# SSL-ingress-Connector

This charm installs a subordinate on the kubernes master and is based on the [kubernetes-deployer](https://github.com/tengu-team/layer-kubernetes-deployer) and 
the SSL-termination-FQDM charm but will now automatically connect your SSL-termination-proxy to the Ingress controller running on your k8s Cluster.


## Configs

It has the same 3 config values as the SSL-termination-proxy:

- **`fqdns`** is a space separated list of domain names on which the webservice should be accessable. Note: make sure to point the DNS records of these domain names to the ssl-termination-proxy. *Example: `"example.com www.example.com"`.*
- **`credentials`** is a space-separated pair of username and password for basic authentication.
- **`contact-email`** is the contact email address for lets encrypt. This email address will receive notifications when the certificate expires. Note that the ssl-termination-proxy automatically renews certificates after 2 months so you will only get an email when something is broken.

## How to use


```bash
# Deploy your ssl-termination-fqdn
juju deploy cs:~tengu-team/ssl-ingress-connector 
# Configure the connector
juju config ssl-ingress-connector fqdns="example.com www.example.com"
juju config ssl-ingress-connector basic_auth="username password"
# Connect the connector with the kubernetes master
juju add-relation kubernets-master ssl-ingress-connector
# Connect the connector with the proxy.
juju add-relation ssl-ingress-connector:ssl-termination ssl-termination-proxy:ssl-termination
```

## Authors

This software was created in the [IDLab research group](https://www.ugent.be/ea/idlab) of [Ghent University](https://www.ugent.be) in Belgium. This software is used in [Tengu](https://tengu.io), a project that aims to make experimenting with data frameworks and tools as easy as possible.

- Sander Borny <sander.borny@ugent.be>
- Merlijn Sebrechts <merlijn.sebrechts@gmail.com>
- Sebastien Pattyn <sebastien.pattyn@tengu.io>
- Crawler icon made by [Vectors Market](https://www.flaticon.com/authors/vectors-market) from [www.flaticon.com](www.flaticon.com) licensed as [Creative Commons BY 3.0](http://creativecommons.org/licenses/by/3.0/)
