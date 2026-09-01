# Distribuir o aplicativo do estudo

> **Decisão em uma linha (ADR-114):** as sessões rodam **só no aplicativo Android instalado**, que
> a equipe entrega por **link direto** com um APK **assinado com a chave do estudo**. O navegador
> serve para o resto (diário, questionários, tela de senha da equipe) e **recusa** iniciar sessão.

## Por que não é só uma preferência

A reprodução **sem alteração do áudio** é decisão inegociável do estudo (#3): o arquivo que o
participante ouve tem de ser exatamente o que foi preparado e validado por FFT. Isso foi verificado
na pilha **nativa** — o Android decodifica o FLAC e devolve o mesmo áudio do WAV.

No navegador, o som passa pela pilha do browser, que **reamostra** para a taxa do dispositivo e
pode aplicar ganho próprio. Ninguém validou esse caminho, e ele muda com navegador, versão e
sistema. Uma sessão ali **pareceria** ter funcionado, e o dado entraria no estudo sem marcação —
por isso a Home simplesmente não oferece o botão na web, e explica isso ao participante.

---

## 1. Criar a chave de assinatura (uma vez, e guardar bem)

A chave dá **identidade** ao aplicativo: é ela que garante que a atualização que o participante
instala veio de vocês. Gere-a uma vez e guarde-a como se guarda um segredo do estudo.

```bash
keytool -genkeypair -v -keystore sereno.jks -keyalg RSA -keysize 4096 \
  -validity 10000 -alias sereno \
  -dname "CN=Estudo Sereno, OU=UNINTA, O=Centro Universitario INTA, L=Sobral, ST=CE, C=BR"
```

> ⚠️ **Perder esta chave é irreversível.** Sem ela não há como publicar uma atualização que o
> celular aceite por cima da instalada — o participante teria de **desinstalar** o app, o que apaga
> o cache de áudio cifrado e obriga a baixar tudo de novo. Guarde o arquivo `sereno.jks` **e** as
> senhas junto da custódia da semente de randomização, com a mesma disciplina.
>
> A validade longa (`-validity 10000`) é o padrão do Android e existe justamente porque a chave
> acompanha o aplicativo por toda a sua vida.

## 2. Cadastrar a chave nos segredos do repositório

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Segredo | Conteúdo |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | o arquivo `.jks` em base64 (comando abaixo) |
| `ANDROID_KEYSTORE_PASSWORD` | senha do keystore |
| `ANDROID_KEY_ALIAS` | `sereno` (o `-alias` usado acima) |
| `ANDROID_KEY_PASSWORD` | senha da chave (igual à do keystore, se não separou) |

```bash
base64 -w0 sereno.jks > sereno.jks.b64     # macOS/Git Bash: base64 -i sereno.jks -o sereno.jks.b64
```

> **Enquanto esses segredos não existirem**, o CI continua gerando o APK — mas com a chave de
> **debug**, e o artefato sai com o nome **`sereno-apk-DEBUG-NAO-DISTRIBUIR`**. É de propósito: um
> APK de debug com nome limpo é o que alguém baixa com pressa e entrega a um participante.
>
> Se um dos quatro segredos faltar, o passo **falha em voz alta** em vez de cair no caminho de
> debug — segredo pela metade é pior que segredo nenhum.

## 3. Pegar o APK e conferir que é o certo

1. **Actions → Build & Deploy (app)** → a execução mais recente → artefato **`sereno-apk`**.
   (Se o nome vier com `DEBUG-NAO-DISTRIBUIR`, pare: volte ao passo 2.)
2. No log do passo *"Assinar o APK para distribuicao"*, anote a linha **`SHA-256 digest`** do
   certificado. **É a impressão digital do estudo** — a mesma em toda versão assinada com a mesma
   chave.
3. Confira o arquivo baixado antes de publicá-lo em qualquer lugar:

```bash
apksigner verify --print-certs app-release.apk | grep -i "SHA-256"
```

A impressão digital tem de ser **idêntica** à do log. Se divergir, o arquivo não é o que o CI
produziu — não distribua.

## 4. Entregar ao participante

**Onde hospedar.** Qualquer lugar que a instituição já use e que dê um link estável: Drive
institucional, pasta do NIT, um diretório no site do curso. O que **não** vale é um link público e
indexável enquanto o piloto está fechado.

**Como instalar** (o participante fará isto uma vez, com a equipe junto, na etapa presencial):

1. Abrir o link no celular Android e baixar o arquivo `.apk`.
2. O Android vai perguntar se permite instalar **desta fonte** — é o comportamento normal para
   aplicativos fora da Play Store. Permitir, e instalar.
3. Abrir o app, informar o **código do estudo** e o código de acesso que chega por e-mail.
4. **Fazer a verificação de fones junto com a equipe.** É o momento de confirmar que os fones do
   participante funcionam nos dois lados — e ela vai se repetir a cada sessão.

> **Antecipe o aviso do Android no recrutamento.** Um alerta de "fonte desconhecida" no meio da
> inclusão assusta e derruba adesão; explicado antes, é só um passo.

## 5. Se o participante não tiver Android

**Ele não é elegível.** O critério de inclusão aprovado diz "smartphone compatível com **a versão
distribuída** do aplicativo", e a versão distribuída é Android (ADR-114, declarado ao CEP no §4b do
dossiê, item D5).

Isso precisa aparecer **no recrutamento**, não na inclusão: descobrir na triagem que a pessoa usa
iPhone, depois de ela ter respondido questionários, é desperdiçar o tempo dela.

---

## Caminho de upgrade: Play Console (teste interno)

Se em algum momento fizer sentido evitar o aviso de "fonte desconhecida":

- Custa **US$ 25, uma vez**, na conta de desenvolvedor Google Play.
- A faixa de **teste interno** aceita até 100 testadores por e-mail, sem revisão demorada.
- **Nada no código muda.** O mesmo APK assinado serve; muda o lugar de onde o participante baixa.
- O custo real não é o dinheiro: é o ciclo de publicação a cada correção durante um piloto de
  quatro semanas.

**iOS continua fora**, e não por escolha de conveniência: exigiria um Mac, conta paga anual e
revisão da App Store — nada disso existe no projeto.

---

## O que a web continua fazendo

Não desligue o app web: ele tem dois papéis que não dependem de áudio.

- **A tela de definição de senha da equipe** (ADR-096) vive nele — é o destino do `?token=` dos
  convites. Sem ela, o convite manda o token cru.
- **Diário, questionários, linha de base, seguimento e relato de evento adverso** funcionam
  normalmente. Travá-los faria o participante perder coleta por um motivo que não se aplica a eles.

O que a web **não** faz é iniciar sessão: ali a Home mostra, no lugar do botão, a explicação de que
as sessões acontecem no aplicativo.
