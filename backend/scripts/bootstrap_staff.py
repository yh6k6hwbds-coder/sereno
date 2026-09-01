"""
scripts/bootstrap_staff.py — Cria as PRIMEIRAS contas de staff (H3, ADR-112).

Sem isto, um banco novo é um sistema em que ninguém entra: `POST /v1/staff` exige a permissão
`user:manage`, que só um staff já existente tem. A tabela nasce vazia na migração inicial e o
`seed_demo.py` não cria staff. É o galo e o ovo do primeiro deploy — e não estava em lista
nenhuma até a Fase H.

**O script NUNCA define senha.** Cada conta nasce com um hash de senha aleatória que ninguém
conhece (o mesmo `unusable_password_hash` do convite, ADR-094) e recebe um **token de uso único**
para a própria pessoa definir a sua. Um `--password` na linha de comando entraria no histórico do
shell, nos logs do provedor e na tela de quem estivesse olhando; e um admin que escolhe a senha de
outro ganha um caminho para assumir a conta alheia, que é justamente o que o ADR-094 fechou.

**Por que existe `--print-link`.** O convite é entregue por e-mail — e no primeiro deploy o SMTP
ainda não está configurado (F3.2), então o e-mail não sai. Sem uma saída, o bootstrap seria
impossível exatamente quando é necessário. Com a flag, o link de uso único é impresso no terminal
de quem opera. **É segredo**: vale uma vez, expira (`STAFF_INVITE_TTL_H`), e não deve ser colado
em chat, ticket ou registro de deploy.

**Dois admins, não um** (ADR-075): o descegamento exige duas pessoas distintas. Uma instalação com
um único admin descobre isso no pior momento — na hora de descegar, no fim do estudo. O script
avisa quando termina com menos de dois.

Uso (dentro do contêiner ou com DATABASE_URL apontado ao banco):
    python scripts/bootstrap_staff.py --check
    python scripts/bootstrap_staff.py --email ana@uninta.edu.br --email bruno@uninta.edu.br \
                                      --print-link
    python scripts/bootstrap_staff.py --email novo@uninta.edu.br --role researcher --force

Sem `--force`, o script se recusa a agir se **já houver staff**: a partir daí o caminho correto é
`POST /v1/staff` pela API, que registra quem convidou quem. `--force` existe para o caso real de
uma instalação que ficou com um admin só e precisa do segundo sem ter como entrar.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select                              # noqa: E402
from sqlalchemy.orm import Session                               # noqa: E402

from app.core.db import get_engine                               # noqa: E402
from app.core.models import StaffUser                            # noqa: E402
from app.modules.audit.service import record_event               # noqa: E402
from app.modules.staff import setup_service                      # noqa: E402

ROLES = ("admin", "researcher")
# Deliberadamente permissivo: validar e-mail a fundo é assunto do provedor. O que se quer pegar
# aqui é o erro de digitação que criaria uma conta inalcançável — sem @, com espaço, vazia.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _existing(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(StaffUser)) or 0)


def _admins(s: Session) -> int:
    return int(s.scalar(select(func.count()).select_from(StaffUser)
                        .where(StaffUser.role == "admin", StaffUser.is_active.is_(True))) or 0)


def _create(s: Session, email: str, role: str, print_link: bool) -> bool:
    """Cria a conta e emite o convite. Devolve False se o e-mail já existia."""
    if s.scalar(select(StaffUser.id).where(StaffUser.email == email)) is not None:
        print(f"ok      {email} — já existe, nada alterado")
        return False

    staff = StaffUser(email=email, password_hash=setup_service.unusable_password_hash(),
                      role=role, mfa_enabled=False)
    s.add(staff)
    s.flush()

    # Auditoria SEM PII: o e-mail não entra na trilha, como em `staff.created` da API. O ator é
    # ``system`` porque não há um staff logado — é exatamente o que este script resolve, e a
    # trilha precisa mostrar que a conta nasceu FORA do fluxo normal de convite.
    record_event(s, action="staff.bootstrapped", resource_type="staff_user",
                 actor_type="system", resource_id=staff.id,
                 meta={"role": role, "printed_link": bool(print_link)})

    token, expires_at = setup_service.issue(s, staff, purpose="invite")
    setup_service.deliver(staff, token, purpose="invite", expires_at=expires_at)
    print(f"criado  {email} ({role}) — convite emitido, expira em "
          f"{expires_at.strftime('%d/%m/%Y %H:%M UTC')}")
    if print_link:
        base = os.getenv("STAFF_SETUP_URL", "").strip()
        alvo = (f"{base}{'&' if '?' in base else '?'}token={token}" if base
                else f"(defina STAFF_SETUP_URL; token cru) {token}")
        print(f"        LINK DE USO ÚNICO — trate como segredo: {alvo}")
    return True


def main(emails: list[str], role: str, check_only: bool, force: bool,
         print_link: bool) -> int:
    with Session(get_engine()) as s:
        total = _existing(s)

        if check_only:
            admins = _admins(s)
            print(f"staff cadastrado: {total}; admins ativos: {admins}")
            if total == 0:
                print("FALTA   nenhuma conta de staff — ninguém consegue entrar no sistema")
            elif admins < 2:
                print("ATENÇÃO o descegamento exige DOIS admins distintos (ADR-075)")
            return 1 if (total == 0 or admins < 2) else 0

        if not emails:
            print("Informe ao menos um --email (ou use --check).")
            return 2
        if total > 0 and not force:
            print(f"RECUSADO já existem {total} conta(s) de staff. A partir daqui, crie pela "
                  f"API (POST /v1/staff), que registra quem convidou quem. Use --force apenas "
                  f"se ninguém consegue entrar.")
            return 1

        invalidos = [e for e in emails if not EMAIL_RE.match(e)]
        if invalidos:
            print(f"RECUSADO e-mail inválido: {', '.join(invalidos)}")
            return 2
        if len(set(emails)) != len(emails):
            print("RECUSADO e-mails repetidos na mesma chamada.")
            return 2

        criados = sum(_create(s, e, role, print_link) for e in emails)
        s.commit()
        admins = _admins(s)

    print(f"\n{criados} conta(s) criada(s). Cada pessoa define a própria senha pelo link; "
          f"o MFA é configurado no primeiro acesso.")
    if role == "admin" and admins < 2:
        print("ATENÇÃO só há um admin ativo. O DESCEGAMENTO exige dois distintos (ADR-075) — "
              "crie o segundo agora, não no fim do estudo.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Cria as primeiras contas de staff do Sereno.")
    ap.add_argument("--email", action="append", default=[],
                    help="e-mail da conta (repita para criar mais de uma)")
    ap.add_argument("--role", choices=ROLES, default="admin")
    ap.add_argument("--check", action="store_true",
                    help="só confere; sai != 0 se não houver staff ou se faltar o 2º admin")
    ap.add_argument("--force", action="store_true",
                    help="cria mesmo já havendo staff (use a API quando alguém já entra)")
    ap.add_argument("--print-link", action="store_true",
                    help="imprime o link de uso único — necessário antes de o SMTP existir")
    a = ap.parse_args()
    sys.exit(main(a.email, a.role, a.check, a.force, a.print_link))
