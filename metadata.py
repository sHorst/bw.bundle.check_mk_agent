def monitored_by_server(check_mk_server):
    for site, site_config in check_mk_server.partial_metadata.get('check_mk', {}).get('sites', {}).items():
        for folder, folder_config in site_config.get('folders').items():
            if not folder_config.get('generated', False):
                continue

            group = folder_config.get('group', None)
            bundle = folder_config.get('bundle', None)
            include_self = folder_config.get('include_self', False)

            if not include_self and check_mk_server.name == node.name:
                continue

            if group and not node.in_group(group):
                continue

            if bundle and not node.has_bundle(bundle):
                continue

            # we monitor this host
            return True

    # no monitoring site found
    return False


@metadata_processor
def add_iptables_rules(metadata):
    metadata.setdefault('check_mk', {})

    check_mk_servers = []
    for check_mk_server in sorted(repo.nodes, key=lambda x: x.name):
        if not check_mk_server.has_bundle('check_mk'):
            continue

        if check_mk_server.partial_metadata == {}:
            return metadata, RUN_ME_AGAIN

        if not monitored_by_server(check_mk_server):
            continue

        check_mk_servers += [check_mk_server, ]

    check_mk_server_ips = []
    interfaces = [metadata.get('main_interface'), ]
    interfaces += metadata['check_mk'].get('additional_interfaces', [])

    for check_mk_server in check_mk_servers:
        for interface, interface_config in check_mk_server.partial_metadata.get('interfaces', {}).items():
            if interface not in interfaces and interface != check_mk_server.partial_metadata.get('main_interface'):
                continue

            check_mk_server_ips += interface_config.get('ip_addresses', [])
            check_mk_server_ips += interface_config.get('ipv6_addresses', [])

    metadata['check_mk']['servers'] = [x.name for x in check_mk_servers]
    metadata['check_mk']['server_ips'] = list(dict.fromkeys(check_mk_server_ips))

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


@metadata_processor
def add_check_mk_tags(metadata):
    metadata.setdefault('check_mk', {})
    metadata['check_mk'].setdefault('tags', [])
    metadata['check_mk']['tags'] += ['cmk-agent', ]

    return metadata, DONE
