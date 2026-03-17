import json
import asyncio
import qrcode
import os
from telethon import TelegramClient

# --- CONFIGURACIÓN DE USUARIO ---

def _load_config():
    try:
        if os.path.exists('../config/config.json'):
            with open('../config/config.json', 'r') as f:
                config = json.load(f)
        else:
            config = {}
    except Exception as e:
        print(f"❌ Error cargando config: {e}")
        config = {}
    return config

async def main():
    print("🔄 Conectando con Telegram...")
    config = _load_config()
    API_ID = config.get("api_id")
    API_HASH = config.get("api_hash")
    SESSION_NAME = config.get("session_name")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        print("✅ ¡Ya estás logueado! No necesitas hacer nada más.")
        print(f"El archivo '{SESSION_NAME}.session' ya es válido.")
        return

    # Si no estás autorizado, iniciamos el proceso de QR
    print("Generando QR de acceso...")
    
    # Solicitamos el login por QR
    qr_login = await client.qr_login()
    
    # Generar la imagen del QR
    img = qrcode.make(qr_login.url)
    img.save("codigo_qr.png")
    print("📸 QR generado como 'codigo_qr.png'. Abriéndolo...")
    
    # Abrir la imagen automáticamente en Windows
    os.startfile("codigo_qr.png")

    print("⏳ Escanea el código con tu celular (Ajustes > Dispositivos > Vincular)...")
    
    # Esperar a que el usuario escanee
    try:
        user = await qr_login.wait() # Espera indefinidamente hasta que escanees
        print(f"\n🎉 ¡Éxito! Logueado como: {user.username}")
        print("✅ El archivo de sesión se ha guardado correctamente.")
        print("Ahora puedes cerrar esto y ejecutar tu script 'TelegramUploader_Secuential.py'")
    except Exception as e:
        print(f"\n❌ Error o tiempo agotado: {e}")
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())