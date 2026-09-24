"""API REST/JSON del módulo Obrador.

Todas las rutas usan el dispatcher ``json2`` de Odoo (el mismo de la API
JSON-2 oficial) y autenticación ``bearer`` con API keys de Odoo generadas con
el scope ``obrador``. Cada petición se ejecuta con los permisos del usuario
dueño de la key, así que rigen los mismos accesos que en la interfaz web.

Los errores se devuelven en el formato JSON estándar de Odoo
(``name``, ``message``, ``arguments``...) con el código HTTP correspondiente.
"""

from datetime import date

from werkzeug.exceptions import BadRequest, Conflict, NotFound

from odoo import Command, fields, http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.http.dispatcher import conceal_debug_traceback

from ..models.obra import ESTADOS_OBRA
from ..models.parte_diario import CLIMAS, ESTADOS_PARTE
from ..models.res_users_apikeys import API_SCOPE

PREFIJO = '/api/obrador/v1'
LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 200

CAMPOS_PARTE = {'obra_id', 'fecha', 'avance', 'clima', 'observaciones', 'consumos', 'equipos'}
CAMPOS_CONSUMO = {'producto_id', 'cantidad', 'notas'}
CAMPOS_EQUIPO = {'equipo_id', 'horas', 'operador'}

RUTA_LECTURA = {
    'type': 'json2',
    'auth': 'bearer',
    'bearer_scope': API_SCOPE,
    'methods': ['GET'],
    'readonly': True,
}
RUTA_ESCRITURA = {
    'type': 'json2',
    'auth': 'bearer',
    'bearer_scope': API_SCOPE,
    'methods': ['POST'],
}


class ObradorApiController(http.Controller):
    @http.route(f'{PREFIJO}/obras', **RUTA_LECTURA)
    @conceal_debug_traceback()
    def listar_obras(self):
        """Obras visibles para el usuario. Filtro opcional: ``estado``."""
        parametros = request.httprequest.args
        dominio = []
        if 'estado' in parametros:
            dominio.append(('estado', '=', _opcion_param(parametros, 'estado', ESTADOS_OBRA)))
        limit, offset = _paginacion(parametros)

        Obra = request.env['obrador.obra']
        obras = Obra.search(dominio, limit=limit, offset=offset, order='codigo')
        return {
            'resultados': [_obra_a_json(obra) for obra in obras],
            'total': Obra.search_count(dominio),
            'limit': limit,
            'offset': offset,
        }

    @http.route(f'{PREFIJO}/partes', **RUTA_LECTURA)
    @conceal_debug_traceback()
    def listar_partes(self):
        """Partes diarios, del más reciente al más antiguo.

        Filtros opcionales: ``obra_id``, ``estado``, ``fecha_desde`` y ``fecha_hasta``.
        """
        parametros = request.httprequest.args
        dominio = []
        if 'obra_id' in parametros:
            dominio.append(('obra_id', '=', _entero_param(parametros, 'obra_id')))
        if 'estado' in parametros:
            dominio.append(('estado', '=', _opcion_param(parametros, 'estado', ESTADOS_PARTE)))
        if 'fecha_desde' in parametros:
            dominio.append(('fecha', '>=', _fecha_param(parametros, 'fecha_desde')))
        if 'fecha_hasta' in parametros:
            dominio.append(('fecha', '<=', _fecha_param(parametros, 'fecha_hasta')))
        limit, offset = _paginacion(parametros)

        Parte = request.env['obrador.parte.diario']
        partes = Parte.search(dominio, limit=limit, offset=offset)
        return {
            'resultados': [_parte_a_json(parte) for parte in partes],
            'total': Parte.search_count(dominio),
            'limit': limit,
            'offset': offset,
        }

    @http.route(f'{PREFIJO}/partes/<int:parte_id>', **RUTA_LECTURA)
    @conceal_debug_traceback()
    def obtener_parte(self, parte_id):
        parte = request.env['obrador.parte.diario'].search([('id', '=', parte_id)])
        if not parte:
            raise NotFound(f'No existe el parte diario {parte_id}.')
        return _parte_a_json(parte)

    @http.route(f'{PREFIJO}/partes', **RUTA_ESCRITURA)
    @conceal_debug_traceback()
    def crear_parte(self, /, **_cuerpo):
        """Crea un parte diario en borrador, con sus consumos y usos de equipo.

        El dispatcher ``json2`` ya pasa el cuerpo como kwargs, pero se vuelve a
        leer para poder rechazar lo que no sea un objeto JSON. ``self`` es
        solo posicional para que una clave "self" en el cuerpo no choque.
        """
        valores = _valores_parte(_cuerpo_json())
        Parte = request.env['obrador.parte.diario']
        if Parte.search_count(
            [('obra_id', '=', valores['obra_id']), ('fecha', '=', valores['fecha'])], limit=1
        ):
            raise Conflict(
                f'Ya existe un parte diario para la obra {valores["obra_id"]} '
                f'con fecha {valores["fecha"]}.'
            )
        parte = Parte.create(valores)
        return request.make_json_response(
            _parte_a_json(parte),
            status=201,
            headers=[('Location', f'{PREFIJO}/partes/{parte.id}')],
        )


# ----------------------------------------------------------------------
# Serialización
# ----------------------------------------------------------------------


def _obra_a_json(obra):
    return {
        'id': obra.id,
        'codigo': obra.codigo,
        'nombre': obra.name,
        'estado': obra.estado,
        'cliente': obra.cliente_id.display_name or None,
        'fecha_inicio': _fecha_a_json(obra.fecha_inicio),
        'avance_actual': obra.avance_actual,
        'fecha_ultimo_parte': _fecha_a_json(obra.fecha_ultimo_parte),
    }


def _parte_a_json(parte):
    return {
        'id': parte.id,
        'referencia': parte.name,
        'obra': {
            'id': parte.obra_id.id,
            'codigo': parte.obra_id.codigo,
            'nombre': parte.obra_id.name,
        },
        'fecha': _fecha_a_json(parte.fecha),
        'avance': parte.avance,
        'clima': parte.clima or None,
        'observaciones': parte.observaciones or None,
        'estado': parte.estado,
        'consumos': [
            {
                'id': consumo.id,
                'producto': {
                    'id': consumo.product_id.id,
                    'nombre': consumo.product_id.display_name,
                },
                'cantidad': consumo.cantidad,
                'unidad': consumo.uom_id.name,
                'notas': consumo.notas or None,
            }
            for consumo in parte.consumo_ids
        ],
        'equipos': [
            {
                'id': uso.id,
                'equipo': {'id': uso.equipo_id.id, 'nombre': uso.equipo_id.name},
                'horas': uso.horas,
                'operador': uso.operador or None,
                'costo': uso.costo,
            }
            for uso in parte.uso_equipo_ids
        ],
        'costo_equipos': parte.costo_equipos,
        'moneda': parte.currency_id.name,
        'cargado_por': {'id': parte.create_uid.id, 'nombre': parte.create_uid.name},
    }


def _fecha_a_json(valor):
    return fields.Date.to_string(valor) if valor else None


# ----------------------------------------------------------------------
# Lectura y validación de la entrada
# ----------------------------------------------------------------------


def _cuerpo_json():
    try:
        datos = request.get_json_data()
    except ValueError:
        datos = None
    if not isinstance(datos, dict):
        raise BadRequest('El cuerpo de la petición debe ser un objeto JSON.')
    return datos


def _valores_parte(datos):
    _sin_campos_desconocidos(datos, CAMPOS_PARTE, 'el parte')
    obra_id = _entero(_requerido(datos, 'obra_id', 'obra_id'), 'obra_id')
    obra = request.env['obrador.obra'].search([('id', '=', obra_id)])
    if not obra:
        raise ValidationError(f'No existe la obra {obra_id}.')

    valores = {
        'obra_id': obra.id,
        'fecha': (
            _fecha(datos['fecha'], 'fecha')
            if datos.get('fecha') is not None
            else fields.Date.context_today(obra)
        ),
        'avance': _numero(_requerido(datos, 'avance', 'avance'), 'avance'),
        'observaciones': _texto(datos.get('observaciones'), 'observaciones'),
        'consumo_ids': [
            Command.create(_valores_consumo(item, f'consumos[{indice}]'))
            for indice, item in enumerate(_lista(datos.get('consumos'), 'consumos'))
        ],
        'uso_equipo_ids': [
            Command.create(_valores_uso_equipo(item, f'equipos[{indice}]'))
            for indice, item in enumerate(_lista(datos.get('equipos'), 'equipos'))
        ],
    }
    if datos.get('clima') is not None:
        valores['clima'] = _opcion(datos['clima'], 'clima', CLIMAS)
    return valores


def _valores_consumo(item, campo):
    _objeto(item, campo)
    _sin_campos_desconocidos(item, CAMPOS_CONSUMO, campo)
    producto_id = _entero(_requerido(item, 'producto_id', campo), f'{campo}.producto_id')
    producto = request.env['product.product'].search(
        [('id', '=', producto_id), ('type', '=', 'consu')]
    )
    if not producto:
        raise ValidationError(f'No existe el material {producto_id} ({campo}.producto_id).')
    return {
        'product_id': producto.id,
        'cantidad': _numero(_requerido(item, 'cantidad', campo), f'{campo}.cantidad'),
        'notas': _texto(item.get('notas'), f'{campo}.notas'),
    }


def _valores_uso_equipo(item, campo):
    _objeto(item, campo)
    _sin_campos_desconocidos(item, CAMPOS_EQUIPO, campo)
    equipo_id = _entero(_requerido(item, 'equipo_id', campo), f'{campo}.equipo_id')
    equipo = request.env['obrador.equipo'].search([('id', '=', equipo_id)])
    if not equipo:
        raise ValidationError(f'No existe el equipo {equipo_id} ({campo}.equipo_id).')
    return {
        'equipo_id': equipo.id,
        'horas': _numero(_requerido(item, 'horas', campo), f'{campo}.horas'),
        'operador': _texto(item.get('operador'), f'{campo}.operador'),
    }


def _sin_campos_desconocidos(datos, permitidos, donde):
    desconocidos = sorted(set(datos) - permitidos)
    if desconocidos:
        raise ValidationError(f'Campos desconocidos en {donde}: {", ".join(desconocidos)}.')


def _requerido(datos, clave, donde):
    if datos.get(clave) is None:
        campo = clave if clave == donde else f'{donde}.{clave}'
        raise ValidationError(f'El campo "{campo}" es obligatorio.')
    return datos[clave]


def _entero(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValidationError(f'El campo "{campo}" debe ser un número entero.')
    return valor


def _numero(valor, campo):
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        raise ValidationError(f'El campo "{campo}" debe ser numérico.')
    return float(valor)


def _texto(valor, campo):
    if valor is None:
        return False
    if not isinstance(valor, str):
        raise ValidationError(f'El campo "{campo}" debe ser texto.')
    return valor


def _fecha(valor, campo):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        raise ValidationError(f'El campo "{campo}" debe ser una fecha AAAA-MM-DD.') from None


def _opcion(valor, campo, opciones):
    validas = [clave for clave, _etiqueta in opciones]
    if valor not in validas:
        raise ValidationError(f'El campo "{campo}" debe ser uno de: {", ".join(validas)}.')
    return valor


def _lista(valor, campo):
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ValidationError(f'El campo "{campo}" debe ser una lista.')
    return valor


def _objeto(valor, campo):
    if not isinstance(valor, dict):
        raise ValidationError(f'Cada elemento de "{campo.split("[")[0]}" debe ser un objeto.')


# Parámetros de la query string (GET): los errores son 400 Bad Request.


def _entero_param(parametros, nombre):
    try:
        return int(parametros[nombre])
    except ValueError:
        raise BadRequest(f'El parámetro "{nombre}" debe ser un número entero.') from None


def _fecha_param(parametros, nombre):
    try:
        return date.fromisoformat(parametros[nombre])
    except ValueError:
        raise BadRequest(f'El parámetro "{nombre}" debe ser una fecha AAAA-MM-DD.') from None


def _opcion_param(parametros, nombre, opciones):
    validas = [clave for clave, _etiqueta in opciones]
    if parametros[nombre] not in validas:
        raise BadRequest(f'El parámetro "{nombre}" debe ser uno de: {", ".join(validas)}.')
    return parametros[nombre]


def _paginacion(parametros):
    limit = _entero_param(parametros, 'limit') if 'limit' in parametros else LIMITE_POR_DEFECTO
    offset = _entero_param(parametros, 'offset') if 'offset' in parametros else 0
    if not 1 <= limit <= LIMITE_MAXIMO:
        raise BadRequest(f'El parámetro "limit" debe estar entre 1 y {LIMITE_MAXIMO}.')
    if offset < 0:
        raise BadRequest('El parámetro "offset" no puede ser negativo.')
    return limit, offset
