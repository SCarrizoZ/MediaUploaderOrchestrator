import os
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes necesarios (Subir videos y gestionar cuenta de youtube)
SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube']

def generate_token():
    secrets_file = "config/client_secrets.json"
    token_file = "config/token.json"

    if not os.path.exists(secrets_file):
        print(f"❌ Error: No se encuentra '{secrets_file}' en esta carpeta.")
        return

    print("🔐 Iniciando proceso de autenticación manual...")
    print("   Se abrirá tu navegador. Por favor inicia sesión con tu cuenta de YouTube.")
    
    try:
        # Configurar el flujo de autorización
        flow = InstalledAppFlow.from_client_secrets_file(secrets_file, SCOPES)
        
        # Lanzar servidor local para recibir el callback
        # Esto bloqueará la terminal hasta que te loguees
        creds = flow.run_local_server(port=0)
        
        # Guardar el token generado
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
        print(f"✅ ¡ÉXITO! Token guardado en '{token_file}'.")
        print("   Ahora puedes ejecutar VideoSegmenterUI sin problemas.")

    except Exception as e:
        print(f"❌ Error durante la autenticación: {e}")

if __name__ == "__main__":
    generate_token()
    input("\nPresiona ENTER para salir...")