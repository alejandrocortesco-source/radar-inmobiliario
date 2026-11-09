"""Login normal. Las credenciales y cookies nunca entran en la configuración de runs."""
import os
import asyncio
import time
import re
from pathlib import Path
from urllib.parse import urlsplit

from metro.extraction import Restricted
from metro.scraper import check_access
from catalogo.fuentes.wasi import RED
from playwright.async_api import Error as BrowserError

LOGIN = 'https://wasi.co/login-usuario.htm'


class AuthBlocked(Restricted):
    pass


def secreto(nombre):
    # Cloud Run puede montar Secret Manager como archivos; local admite entorno.
    archivo = os.getenv(nombre + '_FILE')
    valor = Path(archivo).read_text(encoding='utf-8-sig').rstrip('\r\n') if archivo else os.getenv(nombre)
    if archivo and valor:
        # Admitir archivos privados con una etiqueta explícita, sin copiar ni
        # registrar el contenido. Las variables de entorno se conservan literales.
        etiqueta = r'(?:usuario|user|correo|email)' if nombre == 'WASI_USER' else r'(?:password|contraseña|contrasena|clave)'
        valor = re.sub(r'(?i)^\s*' + etiqueta + r'\s*[:=][ \t]*', '', valor, count=1)
    if not valor:
        raise AuthBlocked('auth_configuration_missing: configura WASI_USER y WASI_PASSWORD fuera del código')
    return valor


async def acceso(page, response=None):
    await check_access(page, response)
    if await page.locator('#login-form:visible').count():
        raise AuthBlocked('auth_session_expired: reanuda para autenticar de nuevo')
    if await page.locator('input[autocomplete="one-time-code"]:visible, input[name*="otp"]:visible').count():
        raise AuthBlocked('auth_interactive_verification: requiere intervención')


async def resolver_sesion_en_uso(page, timeout=45000):
    aviso = page.locator('.modal:visible').filter(has_text='Tu usuario está siendo usado en otros dispositivos')
    if not await aviso.count():
        return False
    if os.getenv('WASI_USE_HERE') != '1':
        raise AuthBlocked('auth_session_in_use: Wasi requiere Usar aquí; detén otras sesiones antes de autorizar el cambio')
    # Acción normal ofrecida por Wasi, únicamente con autorización operativa
    # explícita. No se elimina el modal ni se manipulan tokens o cookies.
    await aviso.get_by_text('Usar aquí', exact=True).click(timeout=timeout)
    await aviso.wait_for(state='hidden', timeout=timeout)
    await acceso(page)
    return True


async def autenticar(context, timeout=45000):
    page = await context.new_page()
    fase = 'open_network'
    try:
        response = await page.goto(RED, wait_until='domcontentloaded', timeout=timeout)
        await check_access(page, response)
        await page.locator('#advanced_search, #login-form').first.wait_for(state='attached', timeout=timeout)
        if await page.locator('#advanced_search').count():
            await page.locator('#id_ciudad').wait_for(state='attached', timeout=timeout)
            return 'session_reused'
        fase = 'read_configuration'
        usuario, password = secreto('WASI_USER'), secreto('WASI_PASSWORD')
        # Destino y formulario verificados; jamás rellenar una redirección ajena.
        destino = urlsplit(page.url)
        if destino.hostname != 'wasi.co' or destino.scheme != 'https' or destino.port not in (None, 443):
            raise AuthBlocked('auth_unexpected_destination')
        await page.locator('#login-form').wait_for(state='visible', timeout=timeout)
        fase = 'fill_user'
        await page.locator('#user').fill(usuario)
        fase = 'fill_password'
        await page.locator('#password').fill(password)
        fase = 'submit_login'
        await page.locator('#login').click(timeout=timeout)
        # Un solo envío por ejecución: un rechazo no se reintenta en bucle.
        limite = time.monotonic() + timeout / 1000
        fase = 'verify_login'
        while time.monotonic() < limite:
            try:
                await check_access(page)
            except BrowserError:
                if page.is_closed():
                    raise
                # La navegación posterior al login puede reemplazar el DOM
                # mientras se consulta. Esperar no vuelve a enviar credenciales.
                await asyncio.sleep(.2)
                continue
            if await page.locator('#alerts-inf-txt:visible').count():
                raise AuthBlocked('auth_rejected: credenciales rechazadas; no se reintenta el envío')
            if await page.locator('input[autocomplete="one-time-code"]:visible, input[name*="otp"]:visible').count():
                raise AuthBlocked('auth_interactive_verification: requiere intervención')
            actual = urlsplit(page.url)
            if actual.hostname != 'wasi.co' or actual.scheme != 'https':
                raise AuthBlocked('auth_unexpected_destination')
            if (actual.path == '/desktop' or actual.path == '/usuario/inmuebles/red') and not await page.locator('#login-form:visible').count():
                break
            await asyncio.sleep(.2)
        else:
            raise AuthBlocked('auth_failed: acceso no confirmado después del envío de credenciales')
        fase = 'verify_network'
        response = await page.goto(RED, wait_until='domcontentloaded', timeout=timeout)
        await acceso(page, response)
        await page.locator('#advanced_search').wait_for(state='visible', timeout=timeout)
        return 'authenticated'
    except AuthBlocked:
        raise
    except Restricted:
        raise AuthBlocked('auth_blocked: CAPTCHA o restricción; no se confirmó acceso') from None
    except Exception as exc:
        # Playwright incluye valores rellenados en algunas excepciones. Nunca
        # conservar texto de excepciones, HTML, trazas ni capturas de autenticación.
        raise AuthBlocked('auth_failed: fase=' + fase + '; tipo=' + type(exc).__name__ + '; acceso no confirmado') from None
    finally:
        await page.close()
