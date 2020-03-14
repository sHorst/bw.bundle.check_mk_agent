from bundlewrap.exceptions import BundleError

supported_versions = {
    '1.4.0p31': 'fb3aacd46e79b15acef947fb390ca678b4f9ad1a1165db4ba0bcff7e5800e51f',
    '1.5.0b3': 'd14b2ef6babcc9f5b36968661cf3106acdcc667f21d954a34adf870d50ceb43c',
    '1.6.0p9': 'c1b5fea31973abb2ecd4795afd87f209cc261d3d78d392495b3c6ffe4f1577a5',
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
    raise BundleError(_(
        "unsupported Agent version {version} for {item} in bundle '{bundle}'"
    ).format(
        version=CHECK_MK_AGENT_VERSION,
        bundle=bundle.name,
        item=item_id,
    ))

CHECK_MK_AGENT_SHA256 = supported_versions[CHECK_MK_AGENT_VERSION]

svc_systemd = {
    'xinetd': {
        'needs': [
            'pkg_apt:xinetd'
        ]
    }
}

pkg_apt = {
    'xinetd': {
        'installed': True,
    }
}

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
        'needs': [
            'download:/tmp/check-mk-agent_{}-1_all.deb'.format(CHECK_MK_AGENT_VERSION),
        ]
    }
}

if node.os == 'debian':
    directories['/usr/lib/check_mk_agent/plugins/3600'] = {
        'mode': '755',
        'owner': 'root',
        'group': 'root',
    }
    downloads['/usr/lib/check_mk_agent/plugins/3600/mk_apt'] = {
        'url': 'https://{server}/{site}/check_mk/agents/plugins/mk_apt'.format(
            server=check_mk_server.hostname,
            site=list(check_mk_server.metadata.get('check_mk', {}).get('sites', {}).keys())[0],
        ),
        'verifySSL': False,
        'sha256': "d9d9865087b1ae20ba4bd45446db84a96d378c555af687d934886219f31fecb0",
        'needs': [
            'directory:/usr/lib/check_mk_agent/plugins/3600',
            'action:install_check_mk_agent'
        ],
        'triggers': ['action:mk_apt_make_exec']
    }
    actions['mk_apt_make_exec'] = {
        'command': 'chmod +x /usr/lib/check_mk_agent/plugins/3600/mk_apt',
        'triggered': True,
    }


files = {
    '/etc/xinetd.d/check_mk': {
        'content_type': 'jinja2',
        'owner': 'root',
        'group': 'root',
        'mode': '0644',
        'context': {
            'ips': ' '.join(sorted(check_mk_config.get('server_ips', []))),
            'port': check_mk_config.get('port', 6556),
        },
        'needs': [
            'pkg_apt:xinetd',
            'action:install_check_mk_agent',
        ],
        'triggers': [
            'svc_systemd:xinetd:restart',
        ]

    }
}
