from bundlewrap.exceptions import BundleError, NoSuchNode

supported_versions = {
    '1.4.0p31': 'fb3aacd46e79b15acef947fb390ca678b4f9ad1a1165db4ba0bcff7e5800e51f',
    '1.5.0b3': 'd14b2ef6babcc9f5b36968661cf3106acdcc667f21d954a34adf870d50ceb43c',
    '1.6.0p9': 'c1b5fea31973abb2ecd4795afd87f209cc261d3d78d392495b3c6ffe4f1577a5',
    '1.6.0p20': '05442e29843f77cd41d8905e852803997303b5a59a86cefc2a0398576f974ef7',
}

check_mk_config = node.metadata.get('check_mk', {})
check_mk_servers = check_mk_config.get('servers', [])

if not check_mk_servers:
    raise BundleError("No Check_mk servers defined for node {node}".format(node=node.name))

# only use first
check_mk_server = repo.get_node(check_mk_servers[0])
check_mk_server_config = check_mk_server.metadata.get('check_mk', {})


CHECK_MK_AGENT_VERSION = check_mk_server_config.get('version', '1.6.0p9')

if CHECK_MK_AGENT_VERSION not in supported_versions.keys():
    raise BundleError(f"unsupported Agent version {CHECK_MK_AGENT_VERSION}")

CHECK_MK_AGENT_SHA256 = supported_versions[CHECK_MK_AGENT_VERSION]

svc_systemd = {
    'check_mk.socket': {
        'needs': [
            'action:install_check_mk_agent',
        ],
    }
}

files = {}
directories = {}

downloads = {
    '/tmp/check-mk-agent_{}-1_all.deb'.format(CHECK_MK_AGENT_VERSION): {
        'url': 'https://{server}/{site}/check_mk/agents/check-mk-agent_{version}-1_all.deb'.format(
            server=check_mk_server.hostname,
            site=list(check_mk_server.metadata.get('check_mk', {}).get('sites', {}).keys())[0],
            version=CHECK_MK_AGENT_VERSION
        ),
        'verifySSL': False,
        'sha256': CHECK_MK_AGENT_SHA256,
        'unless': 'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION)
    }
}
actions = {
    'install_check_mk_agent': {
        'command': 'dpkg -i /tmp/check-mk-agent_{}-1_all.deb'.format(CHECK_MK_AGENT_VERSION),
        'unless': 'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION),
        'cascade_skip': False,
        'needs': [
            'download:/tmp/check-mk-agent_{}-1_all.deb'.format(CHECK_MK_AGENT_VERSION),
        ],
    }
}

# install plugins
for plugin_name, plugin in node.metadata.get('check_mk', {}).get('plugins', {}).items():
    plugin_type = plugin.get('type', None)
    plugin_time = plugin.get('run_every', 300)  # default run every 5 min

    # create Directory, if not exists
    # it will not collide, since i assume, that only this bundle will work in this directory
    directories[f'/usr/lib/check_mk_agent/plugins/{plugin_time}'] = {
        'mode': '755',
        'owner': 'root',
        'group': 'root',
    }

    if plugin_type == 'check_mk_plugin':
        # Download from Monitoring Server. We assume the Plugin is available there
        downloads[f'/usr/lib/check_mk_agent/plugins/{plugin_time}/{plugin_name}'] = {
            'url': 'https://{server}/{site}/check_mk/agents/plugins/{plugin_name}'.format(
                server=check_mk_server.hostname,
                site=list(check_mk_server.metadata.get('check_mk', {}).get('sites', {}).keys())[0],
                plugin_name=plugin_name,
            ),
            'verifySSL': False,
            'sha256': plugin['sha256'],  # This is needed, and will break, if not set
            'needs': [
                f'directory:/usr/lib/check_mk_agent/plugins/{plugin_time}',
                'action:install_check_mk_agent'
            ],
            'mode': '0755',  # make Executable
        }
    else:
        print(f'unknown Plugin Type {plugin_type} for plugin {plugin_name}')

if node.has_bundle('xinetd'):
    # we do not need this file anymore, since systemd will provide the service
    files['/etc/xinetd.d/check_mk'] = {
        'delete': True,
        'triggers': [
            'svc_systemd:xinetd.service:restart',
        ]
    }

# load piggybag file from restic_server
if node.has_bundle('check_mk') and node.has_bundle('restic'):
    cron = [
        '#!/usr/bin/env bash',
        ]

    for backup_hostname, backup_host_config in node.metadata.get('restic', {}).get('backup_hosts', {}).items():
        backup_nodename = backup_hostname
        try:
            backup_node = repo.get_node(backup_hostname)
            backup_hostname = backup_node.hostname
        except NoSuchNode:
            pass

        piggy_file = f'/var/lib/check_mk_agent/spool/piggy_restic_{backup_hostname}'
        if backup_host_config.get('external', False):
            # generate piggy localy
            cron += [
                f'echo "" > {piggy_file}',
            ]

            clients = {}
            for restic_node in sorted(repo.nodes, key=lambda x: x.name):
                if restic_node.metadata.get('restic', {}).get('backup_hosts', {}).get(backup_nodename, None) is None:
                    continue
                clients[restic_node.name] = restic_node.hostname

            for client_nodename, client_hostname in clients.items():
                cron += [
                    f'echo "<<<<{client_hostname}>>>>" >> {piggy_file}',
                    f'echo "<<<local>>>" >> {piggy_file}',
                    f'/opt/restic/restic_last_change_remote.sh {backup_hostname} {client_nodename} >> {piggy_file}',
                ]

            cron += [
                f'echo "<<<<>>>>" >> {piggy_file}',
            ]
        else:
            cron += [
                # ignore, if file does not exists
                f'scp {backup_hostname}:piggy_restic {piggy_file}'
                f' >/dev/null 2>/dev/null || true',
            ]

    files['/etc/cron.hourly/check_mk_agent_get_restic_piggy'] = {
        'content': '\n'.join(cron) + '\n',
        'mode': '0755',
    }

    # generate piggy file on remote server, which we do not control
    files['/opt/restic/restic_last_change_remote.sh'] = {
        'mode': '0755',
    }
