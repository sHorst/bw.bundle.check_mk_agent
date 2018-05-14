
CHECK_MK_AGENT_VERSION = '1.5.0b1-1'
CHECK_MK_AGENT_SHA256 = 'af23d928e3aadc23382846e728effc6d93d14f9e76639d0833143216cafd125c'

check_mk_config = node.metadata.get('check_mk', {})
check_mk_server = repo.get_node(check_mk_config.get('server', ''))

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

downloads = {
    '/tmp/check-mk-agent_{}_all.deb'.format(CHECK_MK_AGENT_VERSION): {
        'url': 'https://{server}/prod/check_mk/agents/check-mk-agent_{version}_all.deb'.format(
            server=check_mk_server.hostname,
            version=CHECK_MK_AGENT_VERSION
        ),
        'sha256': CHECK_MK_AGENT_SHA256,
        'unless': 'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION)
    }
}

actions = {
    'install_check_mk_agent': {
        'command': 'dpkg -i /tmp/check-mk-agent_{}_all.deb'.format(CHECK_MK_AGENT_VERSION),
        'unless': 'dpkg -l | grep check-mk-agent | grep -q {version}'.format(version=CHECK_MK_AGENT_VERSION),
        'needs': [
            'download:/tmp/check-mk-agent_{}_all.deb'.format(CHECK_MK_AGENT_VERSION),
        ]
    }
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
