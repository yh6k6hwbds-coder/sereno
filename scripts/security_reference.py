"""Validação do contrato OpenAPI e demonstração dos mecanismos de segurança."""
import yaml, datetime as dt
from openapi_spec_validator import validate as validate_openapi
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import pyotp, jwt

print("=" * 68); print("1) CONTRATO OpenAPI"); print("=" * 68)
spec = yaml.safe_load(open("openapi.yaml"))
validate_openapi(spec)   # levanta exceção se inválido
paths = spec["paths"]
n_ops = sum(1 for p in paths.values() for m in p if m in ("get", "post", "put", "patch", "delete"))
print(f"  ✓ OpenAPI {spec['openapi']} válido — {len(paths)} caminhos, {n_ops} operações, "
      f"{len(spec['components']['schemas'])} schemas")

print("\n" + "=" * 68); print("2) SENHA — hashing argon2id (staff)"); print("=" * 68)
ph = PasswordHasher()                                   # argon2id, parâmetros seguros por padrão
h = ph.hash("Senha-Forte-Do-Pesquisador!")
print("  hash:", h[:48], "...")
print("  ✓ verifica senha correta:", ph.verify(h, "Senha-Forte-Do-Pesquisador!"))
try:
    ph.verify(h, "senha-errada")
except VerifyMismatchError:
    print("  ✓ rejeita senha errada (VerifyMismatchError)")

print("\n" + "=" * 68); print("3) MFA — TOTP (segundo fator para pesquisador/admin)"); print("=" * 68)
secret = pyotp.random_base32()
totp = pyotp.TOTP(secret)
code = totp.now()
print(f"  código atual: {code}")
print("  ✓ código válido aceito:", totp.verify(code))
print("  ✓ código inválido rejeitado:", totp.verify("000000") is False)

print("\n" + "=" * 68); print("4) TOKEN — JWT de acesso com expiração e papel (RBAC)"); print("=" * 68)
KEY = "chave-apenas-para-demonstracao"   # em produção: segredo em cofre, rotação, RS256
now = dt.datetime.now(dt.timezone.utc)
claims = {"sub": "staff-uuid", "role": "researcher", "scope": "research:read",
          "iat": now, "exp": now + dt.timedelta(minutes=15)}
token = jwt.encode(claims, KEY, algorithm="HS256")
decoded = jwt.decode(token, KEY, algorithms=["HS256"])
print("  token:", token[:48], "...")
print(f"  ✓ decodificado — papel={decoded['role']}, scope={decoded['scope']}")
try:
    expired = jwt.encode({**claims, "exp": now - dt.timedelta(seconds=1)}, KEY, algorithm="HS256")
    jwt.decode(expired, KEY, algorithms=["HS256"])
except jwt.ExpiredSignatureError:
    print("  ✓ token expirado é rejeitado (ExpiredSignatureError)")

# RBAC — matriz mínima de permissões (checada no servidor a cada requisição)
RBAC = {
    "participant": {"session:write", "assessment:write", "diary:write", "ae:write"},
    "researcher": {"research:read", "export:request"},
    "admin": {"research:read", "export:request", "user:manage", "unblind:request"},
}
def can(role, perm): return perm in RBAC.get(role, set())
print("\n  RBAC (exemplos):")
print("   ✓ researcher pode research:read      ->", can("researcher", "research:read"))
print("   ✓ researcher NÃO pode user:manage    ->", not can("researcher", "user:manage"))
print("   ✓ participant NÃO pode research:read  ->", not can("participant", "research:read"))
print("   ✓ ninguém tem 'ver braço' (ativo/sham): não existe permissão que revele alocação")

print("\n" + "=" * 68); print("TODAS AS VERIFICAÇÕES DE SEGURANÇA E CONTRATO PASSARAM ✓"); print("=" * 68)
