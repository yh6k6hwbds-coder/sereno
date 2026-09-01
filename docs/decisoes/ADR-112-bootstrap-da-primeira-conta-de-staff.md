# ADR-112 — A primeira conta de staff: criar sem senha, e cobrar o segundo admin

- **Status:** Aceito
- **Data:** 2026-09-01
- **Decisores:** Arquiteto (Claude), a partir do modelo de acesso do estudo
- **Etapas relacionadas:** 5 (backend), 7 (operação do estudo)
- **Contexto de origem:** item **H3** do `docs/ROADMAP.md`; lacuna nº 1 da auditoria operacional
  de 2026-08-29.
- **Relaciona-se com:** ADR-094 (convite e redefinição por token de uso único), ADR-096 (a tela
  que recebe o link), ADR-075 (descegamento com dois admins), ADR-076 (deploy na Fly).

## Contexto

`POST /v1/staff` exige a permissão `user:manage` — que **só um staff já existente tem**. A tabela
`staff_user` nasce vazia na migração inicial e o `seed_demo.py` não cria staff.

Um banco novo era, portanto, **um sistema em que ninguém entra**. Não havia script, nem passo no
`deploy-fly.md`, nem item de roadmap: a lacuna só apareceu quando alguém perguntou "há outra etapa
faltando?", em agosto. É o caminho crítico do primeiro deploy — antes de qualquer participante,
antes até de conferir se o e-mail funciona.

E há um agravante que só morde no fim: **o descegamento exige dois admins distintos** (ADR-075).
Uma instalação que nasce com um admin só descobre isso no *data lock*, quando a chave selada
precisa ser aberta e falta a segunda pessoa — o momento mais caro possível para consertar.

## Decisão

**`backend/scripts/bootstrap_staff.py`**, idempotente, no mesmo espírito de `seed_protocols.py`.

**Não existe `--password`.** A conta nasce com `unusable_password_hash()` — o hash de uma senha
aleatória que ninguém conhece — e recebe um **token de uso único** para a própria pessoa definir a
sua, exatamente o fluxo do ADR-094. Duas razões, e a segunda é a que importa:

1. Uma senha na linha de comando entra no histórico do shell, nos logs do provedor e na tela de
   quem estiver junto.
2. **Quem opera o deploy não deve ganhar caminho para entrar como a pessoa que acabou de
   cadastrar.** É a mesma regra que o ADR-094 impôs ao admin que convida; um script de bootstrap
   não é motivo para abrir exceção.

**`--print-link` existe porque o SMTP é o item 1 da ordem de deploy e ainda não está de pé.** O
convite é entregue por e-mail; sem e-mail configurado, ele não chega, e o bootstrap seria
impossível justamente quando é necessário. Com a flag, o link de uso único sai no terminal de quem
opera. O script diz, na própria saída, que **é segredo** — vale uma vez, expira, e não deve ser
colado em chat, ticket ou registro de deploy.

**O script cobra o segundo admin.** Ao terminar com menos de dois admins ativos, avisa; e
`--check` sai com código ≠ 0 nesse caso, para que a verificação do deploy falhe em vez de passar
silenciosamente. É barato agora e caro depois.

**Recusa-se a agir havendo staff**, a menos de `--force`. A partir do primeiro acesso, o caminho
correto é `POST /v1/staff`, que registra **quem convidou quem**. `--force` cobre o caso real da
instalação que ficou com um admin só e ninguém consegue entrar.

**A trilha registra ator `system`** e a ação própria `staff.bootstrapped` — não `staff.created`.
Quem auditar vê que a conta nasceu **fora** do fluxo normal de convite, que é precisamente a
informação relevante. Sem PII: o e-mail não entra na trilha, como já acontece no `staff.created`
da API.

**Validação de e-mail deliberadamente frouxa** (`algo@algo.algo`): validar a fundo é assunto do
provedor. O que se quer pegar aqui é o erro de digitação que criaria uma **conta inalcançável** —
sem `@`, com espaço, vazia — porque essa conta não teria como receber o convite nem como ser
consertada por quem ainda não entrou.

Virou o passo **§3.35** do `deploy-fly.md`, entre o `STAFF_SETUP_URL` (§3.3) e o áudio (§3.4) —
nessa ordem porque, sem `STAFF_SETUP_URL`, o link impresso é o token cru.

## Consequências

- O primeiro deploy passa a ter caminho de entrada, e ele está escrito no runbook.
- A verificação de deploy ganha um item que falha: `--check` cobra existir staff **e** haver dois
  admins.
- O `--print-link` é uma superfície nova, ainda que estreita: um link de uso único em terminal.
  Some sozinho (expira, queima no uso) e deixa de ser necessário assim que o SMTP existir (F3.2).
- Nada muda para quem já tem uma instalação em pé — o script se recusa a agir nesse caso.

## Alternativas consideradas

**Criar um admin fixo no `seed_demo.py`.** Rejeitada, e não por pouco: um usuário conhecido com
senha conhecida é uma porta dos fundos que vaza para produção no primeiro `docker compose` mal
copiado. O `seed_demo` existe para a demo local e deve continuar sem staff.

**Uma variável de ambiente `BOOTSTRAP_ADMIN_EMAIL` lida no *startup*.** Rejeitada: cria conta a
cada reinício conforme o ambiente, sem ninguém decidir, e um erro de digitação em segredo do Fly
viraria conta órfã sem trilha clara. Bootstrap é ato deliberado, com um operador presente.

**Um endpoint `POST /v1/staff/bootstrap` liberado enquanto a tabela estiver vazia.** Rejeitada: é
uma rota **pública** de criação de admin, protegida só por uma corrida — quem alcançar o deploy
antes do operador vira admin do estudo. O acesso ao *shell* do servidor já é a credencial certa
para este ato.

**Deixar o operador escolher a senha e trocá-la depois.** Rejeitada: "depois" é onde as senhas
provisórias sobrevivem, e o ADR-094 já tinha decidido que ninguém escolhe a senha de outro.
