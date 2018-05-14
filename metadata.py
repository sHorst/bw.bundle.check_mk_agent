@metadata_processor
def add_iptables_rules(metadata):
    metadata.setdefault('check_mk', {})
    metadata['check_mk'].setdefault('tags', [])

    check_mk_server = repo.get_node(metadata['check_mk'].get('server', ''))

    if check_mk_server.partial_metadata == {}:
        return metadata, RUN_ME_AGAIN

    check_mk_server_ips = []
    interfaces = [metadata.get('main_interface'), ]
    interfaces += metadata['check_mk'].get('additional_interfaces', [])

    for interface, interface_config in check_mk_server.partial_metadata.get('interfaces', {}).items():
        if interface not in interfaces and interface != check_mk_server.partial_metadata.get('main_interface'):
            continue

        check_mk_server_ips += interface_config.get('ip_addresses', [])
        check_mk_server_ips += interface_config.get('ipv6_addresses', [])

    metadata['check_mk']['server_ips'] = list(dict.fromkeys(check_mk_server_ips))
    metadata['check_mk']['tags'] += ['cmk-agent', ]

    if node.has_bundle("iptables"):
        for interface in interfaces:
            for ip in check_mk_server_ips:
                metadata += repo.libs.iptables.accept(). \
                    input(interface). \
                    state_new(). \
                    tcp(). \
                    source(ip). \
                    dest_port(metadata['check_mk'].get('port', 6556))

    return metadata, DONE
