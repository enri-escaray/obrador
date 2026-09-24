from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.obrador.models.res_users_apikeys import API_SCOPE

from .common import ObradorDatosMixin

PREFIJO = '/api/obrador/v1'


@tagged('post_install', '-at_install')
class TestApiObrador(ObradorDatosMixin, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_key = cls._generar_api_key(cls.usuario)

    @classmethod
    def _generar_api_key(cls, usuario, scope=API_SCOPE):
        # En sudo se permite una key sin vencimiento (como haría un administrador).
        return (
            cls.env['res.users.apikeys']
            .with_user(usuario)
            .sudo()
            ._generate(scope, 'Tests API obrador', None)
        )

    def _get(self, ruta, params=None, api_key=None):
        return self.url_open(
            PREFIJO + ruta, params=params, headers=self._cabeceras(api_key or self.api_key)
        )

    def _post(self, ruta, cuerpo, api_key=None):
        return self.url_open(
            PREFIJO + ruta, json=cuerpo, headers=self._cabeceras(api_key or self.api_key)
        )

    @staticmethod
    def _cabeceras(api_key):
        return {'Authorization': f'Bearer {api_key}'}

    def _cuerpo_parte(self, **valores):
        return {
            'obra_id': self.obra.id,
            'fecha': str(self.hoy - timedelta(days=1)),
            'avance': 35.5,
            **valores,
        }

    # ------------------------------------------------------------------
    # Autenticación
    # ------------------------------------------------------------------

    def test_sin_api_key(self):
        respuesta = self.url_open(PREFIJO + '/partes')
        self.assertEqual(respuesta.status_code, 401)
        self.assertIn('bearer', respuesta.headers.get('WWW-Authenticate', '').lower())
        self.assertEqual(respuesta.json()['name'], 'werkzeug.exceptions.Unauthorized')

    def test_api_key_invalida(self):
        respuesta = self._get('/partes', api_key='no-es-una-key-valida')
        self.assertEqual(respuesta.status_code, 401)

    def test_api_key_de_otro_scope_no_sirve(self):
        key_rpc = self._generar_api_key(self.usuario, scope='rpc')
        respuesta = self._get('/partes', api_key=key_rpc)
        self.assertEqual(respuesta.status_code, 401)

    def test_usuario_sin_permisos_del_modulo(self):
        externo = new_test_user(self.env, login='sin_obrador', groups='base.group_user')
        respuesta = self._get('/partes', api_key=self._generar_api_key(externo))
        self.assertEqual(respuesta.status_code, 403)

    # ------------------------------------------------------------------
    # Alta de partes diarios
    # ------------------------------------------------------------------

    def test_crear_parte(self):
        respuesta = self._post(
            '/partes',
            self._cuerpo_parte(
                clima='soleado',
                observaciones='Hormigonado de losa del 2.º piso.',
                consumos=[{'producto_id': self.cemento.id, 'cantidad': 40, 'notas': 'Bolsas'}],
                equipos=[{'equipo_id': self.retro.id, 'horas': 6.5, 'operador': 'Juan Pérez'}],
            ),
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.text)
        datos = respuesta.json()

        parte = self.env['obrador.parte.diario'].browse(datos['id'])
        self.assertTrue(parte.exists())
        self.assertEqual(respuesta.headers['Location'], f'{PREFIJO}/partes/{parte.id}')
        self.assertEqual(parte.create_uid, self.usuario)
        self.assertEqual(parte.estado, 'borrador')
        self.assertEqual(parte.avance, 35.5)
        self.assertEqual(parte.consumo_ids.product_id, self.cemento)
        self.assertEqual(parte.uso_equipo_ids.costo, 325.0)

        self.assertEqual(datos['referencia'], parte.name)
        self.assertEqual(datos['obra']['codigo'], self.obra.codigo)
        self.assertEqual(datos['fecha'], str(self.hoy - timedelta(days=1)))
        self.assertEqual(datos['observaciones'], 'Hormigonado de losa del 2.º piso.')
        self.assertEqual(datos['consumos'][0]['cantidad'], 40.0)
        self.assertEqual(datos['equipos'][0]['operador'], 'Juan Pérez')
        self.assertEqual(datos['costo_equipos'], 325.0)
        self.assertEqual(datos['cargado_por']['id'], self.usuario.id)

    def test_crear_parte_sin_fecha_usa_hoy(self):
        cuerpo = self._cuerpo_parte()
        del cuerpo['fecha']
        respuesta = self._post('/partes', cuerpo)
        self.assertEqual(respuesta.status_code, 201, respuesta.text)
        parte = self.env['obrador.parte.diario'].browse(respuesta.json()['id'])
        self.assertEqual(parte.fecha, fields.Date.context_today(parte.with_user(self.usuario)))

    def test_crear_parte_datos_invalidos(self):
        casos = {
            'falta obra_id': {'avance': 10},
            'falta avance': {'obra_id': self.obra.id},
            'avance no numérico': self._cuerpo_parte(avance='mucho'),
            'avance fuera de rango': self._cuerpo_parte(avance=150),
            'obra inexistente': self._cuerpo_parte(obra_id=999999),
            'fecha mal formada': self._cuerpo_parte(fecha='24/09/2026'),
            'clima desconocido': self._cuerpo_parte(clima='nieve'),
            'campo desconocido': self._cuerpo_parte(avanze=10),
            'consumos no es lista': self._cuerpo_parte(consumos={'producto_id': 1}),
            'consumo sin cantidad': self._cuerpo_parte(consumos=[{'producto_id': self.cemento.id}]),
            'equipo inexistente': self._cuerpo_parte(equipos=[{'equipo_id': 999999, 'horas': 2}]),
            'horas fuera de rango': self._cuerpo_parte(
                equipos=[{'equipo_id': self.retro.id, 'horas': 30}]
            ),
        }
        for caso, cuerpo in casos.items():
            with self.subTest(caso=caso):
                respuesta = self._post('/partes', cuerpo)
                self.assertEqual(respuesta.status_code, 422, respuesta.text)
                self.assertTrue(respuesta.json()['message'])
        self.assertFalse(self.obra.parte_ids, 'Ningún pedido inválido debe crear partes')

    def test_crear_parte_cuerpo_que_no_es_objeto(self):
        respuesta = self._post('/partes', [self._cuerpo_parte()])
        self.assertEqual(respuesta.status_code, 400)

    def test_crear_parte_json_mal_formado(self):
        respuesta = self.url_open(
            PREFIJO + '/partes',
            data='{"obra_id": ',
            headers={**self._cabeceras(self.api_key), 'Content-Type': 'application/json'},
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_crear_parte_duplicado(self):
        self.assertEqual(self._post('/partes', self._cuerpo_parte()).status_code, 201)
        respuesta = self._post('/partes', self._cuerpo_parte(avance=36))
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(len(self.obra.parte_ids), 1)

    def test_crear_parte_en_obra_que_no_esta_en_curso(self):
        self.obra.action_suspender()
        respuesta = self._post('/partes', self._cuerpo_parte())
        self.assertEqual(respuesta.status_code, 422)
        self.assertIn('en curso', respuesta.json()['message'])

    # ------------------------------------------------------------------
    # Consulta de partes diarios
    # ------------------------------------------------------------------

    def test_listar_partes_con_filtros_y_paginacion(self):
        otra_obra = self._crear_obra('Otra obra')
        antiguo = self._crear_parte(dias_atras=10, avance=20.0)
        reciente = self._crear_parte(dias_atras=2, avance=30.0)
        self._crear_parte(dias_atras=5, obra=otra_obra)
        reciente.action_confirmar()

        datos = self._get('/partes', {'obra_id': self.obra.id}).json()
        self.assertEqual(datos['total'], 2)
        self.assertEqual([p['id'] for p in datos['resultados']], [reciente.id, antiguo.id])

        pagina = self._get('/partes', {'obra_id': self.obra.id, 'limit': 1, 'offset': 1}).json()
        self.assertEqual(pagina['total'], 2)
        self.assertEqual([p['id'] for p in pagina['resultados']], [antiguo.id])

        confirmados = self._get('/partes', {'obra_id': self.obra.id, 'estado': 'confirmado'})
        self.assertEqual([p['id'] for p in confirmados.json()['resultados']], [reciente.id])

        desde = str(self.hoy - timedelta(days=6))
        recientes = self._get('/partes', {'obra_id': self.obra.id, 'fecha_desde': desde})
        self.assertEqual([p['id'] for p in recientes.json()['resultados']], [reciente.id])

        hasta = str(self.hoy - timedelta(days=6))
        antiguos = self._get('/partes', {'obra_id': self.obra.id, 'fecha_hasta': hasta})
        self.assertEqual([p['id'] for p in antiguos.json()['resultados']], [antiguo.id])

    def test_listar_partes_parametros_invalidos(self):
        for params in (
            {'limit': 'diez'},
            {'limit': 0},
            {'limit': 500},
            {'offset': -1},
            {'obra_id': 'abc'},
            {'estado': 'aprobado'},
            {'fecha_desde': '2026-13-01'},
        ):
            with self.subTest(params=params):
                self.assertEqual(self._get('/partes', params).status_code, 400)

    def test_obtener_parte(self):
        parte = self._crear_parte(consumo_ids=[self._linea_consumo(cantidad=2)])
        respuesta = self._get(f'/partes/{parte.id}')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos['id'], parte.id)
        self.assertEqual(datos['consumos'][0]['producto']['id'], self.cemento.id)

    def test_obtener_parte_inexistente(self):
        self.assertEqual(self._get('/partes/999999').status_code, 404)

    # ------------------------------------------------------------------
    # Obras
    # ------------------------------------------------------------------

    def test_listar_obras(self):
        planificada = self._crear_obra('Obra futura', iniciar=False)

        datos = self._get('/obras', {'estado': 'en_curso'}).json()
        ids = [obra['id'] for obra in datos['resultados']]
        self.assertIn(self.obra.id, ids)
        self.assertNotIn(planificada.id, ids)

        obra = next(o for o in datos['resultados'] if o['id'] == self.obra.id)
        self.assertEqual(obra['codigo'], self.obra.codigo)
        self.assertEqual(obra['estado'], 'en_curso')
        self.assertEqual(obra['fecha_inicio'], str(self.obra.fecha_inicio))
