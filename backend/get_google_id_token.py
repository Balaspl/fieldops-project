from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_CONFIG = {
    "web": {
        "client_id": "194058811211-pe27lf6malmd6e985vjbtgh62l3jjbud.apps.googleusercontent.com",
        "client_secret": "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",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [
            "http://localhost:8080/"
        ],
    }
}

flow = InstalledAppFlow.from_client_config(
    CLIENT_CONFIG,
    scopes=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
)

credentials = flow.run_local_server(
    host="localhost",
    port=8080,
    prompt="consent",
    open_browser=True,
)

print("\nACCESS TOKEN:")
print(credentials.token)

print("\nID TOKEN:")
print(credentials.id_token)



























