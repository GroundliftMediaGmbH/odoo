{
    'name': 'Groundlift - 2FA trusted devices (14 days)',
    'summary': 'Automatically trusts a browser/device for 14 days after successful TOTP verification.',
    'version': '19.0.1.0.0',
    'category': 'Technical/Security',
    'author': 'Groundlift',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'web',
        'auth_totp',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
