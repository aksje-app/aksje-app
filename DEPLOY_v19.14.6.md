# Deploy v19.14.6

## GitHub

Legg deltaen på den eksisterende stabiliseringsgrenen og push én commit.

## Render

Build Command skal være:

```text
pip install -r requirements.txt && python tools/check_runtime_dependencies.py
```

Start Command skal være:

```text
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
```

Behold testmiljøets persistente lagringsoppsett og sikkerhetsbrytere. Ikke legg inn `STREAMLIT_SERVER_USE_STARLETTE`.

## Verifisering før nytt UTKAST

I deployloggen skal avhengighetssmoken vise `ok: true`, én PDF-side og `marker_found: true`. Først deretter kjøres ett nytt UTKAST.
