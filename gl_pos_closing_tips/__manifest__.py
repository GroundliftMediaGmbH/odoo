{
    'name': 'Groundlift POS Closing Tips',
    'version': '19.0.1.0.0',
    'summary': 'Show recorded tips in the POS closing screen',
    'category': 'Point of Sale',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'assets': {
        'point_of_sale._assets_pos': [
            'gl_pos_closing_tips/static/src/js/closing_tips.js',
        ],
    },
    'installable': True,
    'application': False,
}
