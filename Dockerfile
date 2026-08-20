# Onde ir? (RAM, protótipo SESARAM) — imagem Docker (v0.13.0)
#
# Construir e correr:
#     docker build -t onde-ir .
#     docker run --rm -p 8000:8000 onde-ir
# (ou, mais simples: docker compose up --build)
#
# Depois abrir http://127.0.0.1:8000 — a imagem serve a API e o frontend
# no mesmo processo, tal como em desenvolvimento.
#
# Notas de desenho:
# - python:3.12-slim: pequena e suficiente (todas as dependências têm
#   wheels; não é preciso compilador).
# - As dependências instalam-se ANTES de copiar o código, para que uma
#   alteração ao código não invalide a camada (cache) do pip.
# - Corre como utilizador não-root ("app"): boa prática, e o único
#   ficheiro que a aplicação escreve (app/data/espera_cache.json, o
#   cache dos tempos de espera) fica dentro da pasta dele.
# - HEALTHCHECK usa o endpoint /api/saude já existente, via urllib da
#   biblioteca padrão — a imagem slim não traz curl e não vale a pena
#   instalá-lo só para isto.

FROM python:3.12-slim

# Sem .pyc no disco; logs sem buffer (aparecem logo no docker logs).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 1) Dependências (camada estável, aproveita o cache entre builds).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Código e dados (camada que muda a cada versão).
COPY . .

# 3) Utilizador sem privilégios, dono da pasta (para o cache de espera).
RUN useradd --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Se o /api/saude não responder "ok", o Docker marca o contentor como
# unhealthy (visível em docker ps / usado pelo compose e orquestradores).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
r=urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4); \
sys.exit(0 if r.status==200 else 1)"

# --proxy-headers: respeita X-Forwarded-* se um dia ficar atrás de um
# reverse proxy (nginx/traefik) na rede do SESARAM.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
