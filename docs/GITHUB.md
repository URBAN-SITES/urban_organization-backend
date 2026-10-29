# Integração com GitHub

O Inceptum usa **um GitHub App**, não um OAuth App. O GitHub App dá permissões
granulares por repositório: a pessoa escolhe em quais repositórios instala o app.
Os tokens de usuário expiram em 8 horas e são renovados. O próprio app lê os
repositórios com um token de instalação de 1 hora, sem depender da conta de quem
está vendo a tela.

O código fica em `core/modules/github/`.

## O que existe

São dois fluxos separados que usam o mesmo app:

| Fluxo | Para que serve | Guarda token? |
|---|---|---|
| **Entrar com GitHub** (`purpose=login`), **vincular login** (`purpose=link`) | Criar a conta ou entrar nela. Vincula pelo e-mail verificado e primário do GitHub, ou pela identidade já vinculada | **Não.** O token é usado para ler `/user` e `/user/emails` e é revogado na hora |
| **Conectar repositórios** (`purpose=connect`) | Listar os repositórios que a pessoa alcança pelas instalações do app | Sim: `GitHubConnection`, com access e refresh token **criptografados** (`EncryptedTextField`) |

O e-mail e a senha continuam funcionando. Uma conta que só entra pelo GitHub (sem
senha) não pode desvincular o login antes de definir uma senha em "Esqueci a senha".

**Desconectar** chama `DELETE /applications/{client_id}/grant`. Isso revoga a
autorização no GitHub e apaga os tokens do banco. Os repositórios já associados a
projetos continuam funcionando, porque usam o token da instalação, não o da pessoa.

## 1. Criar o GitHub App

Em GitHub, vá em **Settings → Developer settings → GitHub Apps → New GitHub App**.
Para uma organização, o caminho é **Organization settings → Developer settings**.

| Campo | Valor |
|---|---|
| GitHub App name | `Inceptum` (ou `Inceptum Dev` para o ambiente local) |
| Homepage URL | URL do frontend, por exemplo `https://michalski.app` |
| Callback URL | `<FRONTEND_URL>/integrations/github/callback`. Para desenvolvimento, adicione também `http://localhost:5173/integrations/github/callback` |
| Expire user authorization tokens | **Ligado** (o backend renova sozinho) |
| Request user authorization (OAuth) during installation | **Desligado**: o login e a conexão começam no Inceptum, que gera o `state` assinado |
| Setup URL | `<FRONTEND_URL>/integracoes/github` |
| Redirect on update | Ligado |
| Webhook | Ativo. URL `<BACKEND_URL>/api/v1/integrations/github/webhook/` |
| Webhook secret | Um valor aleatório longo (`openssl rand -hex 32`) que também vai para o `.env` |
| Where can this GitHub App be installed? | "Any account" para que outras pessoas e organizações instalem. "Only on this account" para testes |

### Permissões mínimas

As permissões de repositório são todas **somente leitura**:

| Permissão | Acesso | Usada para |
|---|---|---|
| Metadata | Read | Obrigatória. Lista repositórios |
| Contents | Read | Branches |
| Pull requests | Read | PRs recentes e vínculo na tarefa |
| Issues | Read | Issues recentes |
| Checks | Read | Status dos checks dos PRs abertos |

Há uma única permissão de conta:

| Permissão | Acesso | Usada para |
|---|---|---|
| Email addresses | Read | Login: achar o e-mail verificado da pessoa |

O app não pede nenhuma permissão de escrita. Ele nunca altera um repositório.

### Eventos assinados

`Pull request`, `Issues`, `Create`, `Delete`, `Push`, `Check run` e `Repository`.

O webhook confere `X-Hub-Signature-256` (HMAC-SHA256 do corpo com o secret) antes
de qualquer coisa. Em seguida:

- atualiza o título e o estado (aberto, rascunho, fechado, mergeado) dos PRs
  vinculados a tarefas;
- marca uma branch vinculada como apagada;
- acompanha a renomeação do repositório;
- invalida o cache de 60 s da aba GitHub do projeto.

### Chave privada

Em **Private keys → Generate a private key**, o GitHub baixa um `.pem`. Coloque o
conteúdo em `GITHUB_APP_PRIVATE_KEY`. Nunca faça commit desse arquivo.

## 2. Variáveis do `.env` (backend)

```env
GITHUB_APP_ID=123456              # "App ID" na página do app
GITHUB_APP_SLUG=inceptum          # o final de https://github.com/apps/<slug>
GITHUB_CLIENT_ID=Iv23li...        # "Client ID"
GITHUB_CLIENT_SECRET=...          # "Generate a new client secret"
GITHUB_APP_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n"
GITHUB_WEBHOOK_SECRET=...         # o mesmo valor configurado no app
GITHUB_OAUTH_REDIRECT_URI=        # opcional; padrão: $FRONTEND_URL/integrations/github/callback
```

O frontend não recebe nenhuma dessas variáveis. Ele só pede a URL de autorização
ao backend.

Sem `GITHUB_CLIENT_ID` e `GITHUB_CLIENT_SECRET`, os endpoints respondem 503 com
`code: github_not_configured`, e a tela mostra "Integração não configurada".

Sem `GITHUB_APP_ID` e `GITHUB_APP_PRIVATE_KEY`, o login e a lista de repositórios
funcionam. Já a aba GitHub do projeto e o vínculo na tarefa respondem 503.

O token de instalação fica no cache do Django (Redis em produção) até 1 minuto
antes de expirar.

## 3. Endpoints (`/api/v1/`)

| Método e rota | Quem pode |
|---|---|
| `GET integrations/github/authorize/?purpose=login\|link\|connect` | `login` é anônimo. Os outros pedem sessão |
| `POST integrations/github/callback/` `{code, state}` | `state` assinado, com validade de 10 min e preso ao usuário em `link` e `connect`. `login` grava os mesmos cookies JWT do login por e-mail |
| `GET integrations/github/` | Status: configurado, identidade, conexão, URL de instalação |
| `DELETE integrations/github/connection/` | Revoga a autorização e apaga os tokens |
| `DELETE integrations/github/identity/` | Desvincula o login. Exige senha definida |
| `GET integrations/github/repositories/?search&visibility&language&page&refresh` | Repositórios autorizados, em páginas de 20. A busca e os filtros rodam no servidor. Cache de 2 min, e `refresh=true` força uma nova leitura |
| `GET/POST sectors/<id>/repositories/` `{github_ids: [...]}` | Ler: leitor do projeto. Associar: **gestor**, e o repositório precisa estar na lista dele. Duplicatas são recusadas com 400 |
| `DELETE sectors/<id>/repositories/<repo>/` | Gestor. Remove só a associação e os vínculos das tarefas. Não toca no GitHub |
| `GET github/repositories/<repo>/activity/` | Leitor. 10 branches, PRs e issues recentes, com checks dos 5 PRs abertos mais recentes |
| `GET/POST tasks/<id>/github/`, `DELETE tasks/<id>/github/<link>/`, `GET tasks/<id>/github/search/?q=` | Ler: leitor. Vincular, desvincular e buscar: editor |
| `POST integrations/github/webhook/` | GitHub, com assinatura obrigatória |

### Erros que a interface explica

Os erros do GitHub voltam com um `code` estável no corpo:

| HTTP | `code` | Quando |
|---|---|---|
| 429 | `github_rate_limited` (+ `reset_at`) | Limite da API do GitHub (`x-ratelimit-remaining: 0` ou 429) |
| 409 | `github_not_connected` | Token revogado, refresh expirado ou conexão ausente. O backend apaga a conexão inválida. Usa 409, e não 401, para não derrubar a sessão do Inceptum |
| 403 | `github_forbidden` | O app não tem permissão, ou a instalação perdeu acesso ao repositório |
| 502 | `github_unavailable` | Falha de rede ou 5xx do GitHub |
| 503 | `github_not_configured` | Faltam variáveis do `.env` |

A paginação da API do GitHub segue o cabeçalho `Link: rel="next"` (100 itens por
página, no máximo 1000 repositórios por usuário).

## 4. Testes

`core/modules/github/tests/` simula todas as respostas do GitHub (`FakeGitHub` em
`helpers.py`) e gera uma chave RSA de teste para o JWT do app. Os testes cobrem:

- login, vínculo e conexão;
- tokens criptografados;
- renovação, e o caso em que ela falha;
- revogação;
- `state` adulterado;
- busca, filtros e paginação;
- rate limit e token revogado;
- permissões de gestor, editor, leitor e de quem está de fora;
- checks;
- vínculo de tarefa;
- assinatura do webhook.

```bash
SECRET_KEY=ci-only FIELD_ENCRYPTION_KEY=<chave Fernet> python manage.py test core.modules.github
```

Nenhum teste chama o GitHub de verdade. O teste real depende de um app criado
conforme a seção 1.

### Teste manual com um app real

1. Crie o app conforme a seção 1, com Callback URL `http://localhost:5173/integrations/github/callback`.
2. Preencha o `.env` do backend e reinicie.
3. Para receber webhooks localmente, use um túnel. Por exemplo, `smee.io` com
   `npx smee -u <canal> -t http://127.0.0.1:8000/api/v1/integrations/github/webhook/`.
   Use o canal como Webhook URL do app.
4. No Inceptum, abra **Configurações → GitHub → Conectar**, instale o app em um
   repositório e associe esse repositório a um projeto.
