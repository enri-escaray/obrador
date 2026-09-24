{
    'name': 'Obrador',
    'version': '20.0.1.0.0',
    'summary': 'Gestión de obras: partes diarios, consumo de materiales y uso de equipos',
    'description': """
Gestión de obras para empresas constructoras
============================================

* Obras con ciclo de vida (planificada, en curso, suspendida, finalizada).
* Partes diarios con avance físico, clima y observaciones.
* Consumo de materiales (productos de Odoo) y horas de uso de equipos.
* API REST/JSON autenticada con API keys de Odoo (scope ``obrador``).
""",
    'category': 'Services',
    'author': 'Enrique Escaray',
    'website': 'https://github.com/enri-escaray/obrador',
    'license': 'LGPL-3',
    'depends': ['mail', 'product'],
    'data': [
        'security/obrador_security.xml',
        'data/ir_sequence_data.xml',
        'views/obra_views.xml',
        'views/parte_diario_views.xml',
        'views/equipo_views.xml',
        'views/reporte_views.xml',
        'views/menus.xml',
        'security/ir.access.csv',
    ],
    'demo': [
        'demo/obrador_demo.xml',
    ],
    'application': True,
}
