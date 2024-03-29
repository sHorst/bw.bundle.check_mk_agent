from bundlewrap.exceptions import BundleError, NoSuchNode
global node, repo

supported_versions = {
    '1.4.0p31': 'fb3aacd46e79b15acef947fb390ca678b4f9ad1a1165db4ba0bcff7e5800e51f',
    '1.5.0b3': 'd14b2ef6babcc9f5b36968661cf3106acdcc667f21d954a34adf870d50ceb43c',
    '1.6.0p9': 'c1b5fea31973abb2ecd4795afd87f209cc261d3d78d392495b3c6ffe4f1577a5',
    '1.6.0p20': '05442e29843f77cd41d8905e852803997303b5a59a86cefc2a0398576f974ef7',
    '2.0.0p2': '417251a9f33db0516d98e39be68269f8439eeed0f14218cdc23aadf7bdfadcb4',
    '2.0.0p13': '13497d7c2a0c4a3e1ed8bd6237cdd26cab120aa6b9b3952e7dcd4f260aca47b2',
    '2.1.0p30': 'f4badac0811e898812387fa9e5efab5e0c6ab28e79b6cc9478249bd4bb5e1e24',
    '2.2.0p4': 'c84af3b0cc249c09b818b0de15200f9ebe7db41127e8931c04f564a0495b3f0d',
}

check_mk_config = node.metadata.get('check_mk', {})
check_mk_servers = check_mk_config.get('servers', [])
check_mk_servers_site = check_mk_config.get('servers_site', {})

if not check_mk_servers:
    raise BundleError("No Check_mk servers defined for node {node}".format(node=node.name))

# only use first
first_check_mk_server = repo.get_node(check_mk_servers[0])
first_check_mk_server_config = first_check_mk_server.metadata.get('check_mk', {})
first_check_mk_server_site = check_mk_servers_site.get(first_check_mk_server.name)  # fail if there is no site

first_check_mk_server_base_url = f'https://{first_check_mk_server.hostname}/{first_check_mk_server_site}'

CHECK_MK_AGENT_VERSION = first_check_mk_server_config.get('version', '1.6.0p9')
CHECK_MK_AGENT_MAJOR_VERSION = int(CHECK_MK_AGENT_VERSION.split('.')[0])
CHECK_MK_AGENT_MINOR_VERSION = int(CHECK_MK_AGENT_VERSION.split('.')[1])

if CHECK_MK_AGENT_VERSION not in supported_versions.keys():
    raise BundleError(f"unsupported Agent version {CHECK_MK_AGENT_VERSION}")

CHECK_MK_AGENT_SHA256 = supported_versions[CHECK_MK_AGENT_VERSION]

if (CHECK_MK_AGENT_MAJOR_VERSION == 2 and CHECK_MK_AGENT_MINOR_VERSION >= 2) or CHECK_MK_AGENT_MAJOR_VERSION > 2:
    svc_systemd = {
        'check-mk-agent.socket': {
            'needs': [
                'action:install_check_mk_agent',
            ],
        }
    }

else:
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
        'url': f'{first_check_mk_server_base_url}/check_mk/agents/check-mk-agent_{CHECK_MK_AGENT_VERSION}-1_all.deb',
        'verifySSL': False,
        'sha256': CHECK_MK_AGENT_SHA256,
        'unless': 'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION)
    }
}
actions = {
    'install_check_mk_agent': {
        'command': 'dpkg --force-confold -i /tmp/check-mk-agent_{}-1_all.deb'.format(CHECK_MK_AGENT_VERSION),
        'unless': 'test ! -f /tmp/check-mk-agent_{version}-1_all.deb || '
                  'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION),
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
            'url': f'{first_check_mk_server_base_url}/check_mk/agents/plugins/{plugin_name}',
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

# TODO: find out, if agent is running

# register TLS with all check_mk_servers
for check_mk_server_name in check_mk_servers:
    check_mk_server = repo.get_node(check_mk_server_name)
    check_mk_server_site = check_mk_servers_site.get(check_mk_server.name)

    automation_password = repo.vault.password_for(f'check_mk_automation_secret_{check_mk_server.name}_{check_mk_server_site}').value

    actions[f'register_with_check_mk_server_{check_mk_server.name}_{check_mk_server_site}'] = {
        'command': f'cmk-agent-ctl register --hostname {node.hostname} --server {check_mk_server.hostname} --trust-cert --site {check_mk_server_site} --user automation --password {automation_password}',
        'unless': f'cmk-agent-ctl status | grep {check_mk_server.hostname}/{check_mk_server_site}',
        'cascade_skip': False,
        'needs': [
            'action:install_check_mk_agent',
        ],
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
                f'rsync -a {backup_hostname}:piggy_restic {piggy_file}'
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
