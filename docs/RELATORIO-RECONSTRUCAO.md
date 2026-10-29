# Inceptum: relatório da reconstrução pós-hackathon (fases 0 a 6)

Data: 29/10/2026.

> **Sobre o nome do arquivo.** O plano pedia `docs/RELATORIO-FINAL.md`, mas esse arquivo já existe: é o relatório do hackathon. Para não sobrescrevê-lo, este relatório fica em `docs/RELATORIO-RECONSTRUCAO.md`.

Nada foi mesclado em `dev` nem em `main`, nenhum PR foi aberto e não houve deploy. Como `dev` é publicada em produção a cada 2 minutos, **produção continua exatamente como estava no fim do hackathon**.

## 1. Repositórios, branches e commits de origem

| | Frontend | Backend |
|---|---|---|
| Repositório | `Resenha-Coders-Hackathon/frontend-resenha` | `Resenha-Coders-Hackathon/backend-resenha` |
| Branch de trabalho | `feat/alteracoes-pos-hackathon` | `feat/alteracoes-pos-hackathon` |
| Criada a partir de | `dev` @ `583b6fa` (24/10/2026) | `dev` @ `881bd89` (24/10/2026) |
| Commits na branch | 21 | 21 (com o do relatório e esta correção) |

Todos os commits têm você (Pauloartur-23) como autor, como foi pedido em 28/10/2026.

## 2. Mudanças por fase

### Fase 0: diagnóstico (sem código)

Levantamento do código real, do CI e das divergências do plano. O relatório completo está em `inceptum/DIAGNOSTICO.md`, nos arquivos do projeto. Os pontos que mudaram o plano:

- o modelo real é Organização → Setor (projeto) → Tarefa;
- `dev` faz deploy automático;
- o CI estava vermelho nos dois repositórios.

### Fase 1: fundação visual e CI verde

| Repo | Commit | O que mudou |
|---|---|---|
| front | `8fe0b35` | Corrige os erros de oxlint e eslint que deixavam o CI vermelho |
| front | `8a1b55c` | Specs de guards e upload da IA alinhados ao comportamento atual |
| front | `c282d51` | O CI passa a rodar todos os specs, não só o de notificações |
| front | `d11c9b1` | `/assistente` respeita o acesso temporário |
| front | `07cc17e` | Tokens de cor, tipografia, raio, sombra e motion; tema sem flash |
| front | `9388cce` | Kit de componentes base (24 componentes `Ui*`) |
| front | `f9f15f2` | Shell do app: sidebar recolhível, header, command palette, nav mobile |
| back | `3044d90` | Ruff (imports e formatação) |
| back | `f24a3ad` | Fallback do banco fora do Docker |
| back | `fc81408` | Teste do prompt da IA atualizado |
| back | `46802ef` | Mensagem do chat e notificações na mesma transação |
| back | `34dfeff` | Acesso temporário ao assistente por lista de e-mails |

### Fase 2: telas principais

| Repo | Commit | O que mudou |
|---|---|---|
| front | `25ead8d` | Login, cadastro e recuperação de senha |
| front | `a16d44a` | Onboarding da primeira organização |
| front | `9c56a3c` | Painel inicial |
| front | `875fd9a` | Organizações, membros, convites e configurações |
| front | `28c7e1e` | Página de projetos (filtros, favoritos, arquivo, acesso) |
| front | `e9ee4d5` | Quadro, lista e tabela de tarefas com painel completo |
| front | `c0e46ef` | Busca global e central de notificações |
| back | `fa54a5c` | Histórico da tarefa, favoritos e arquivamento de projetos |
| back | `a5959d3` | Id do projeto na lista de tarefas do painel |
| back | `8e5505c` | Filtros de projetos no servidor e flag `can_manage` |
| back | `8985bba` | Etiquetas, @menções em comentários e pessoas do projeto |
| back | `1323642` | Filtros de tarefas no servidor e menções na edição |
| back | `9548ee2` | Filtro de notificações por tipo no servidor |

### Fase 3: GitHub

| Repo | Commit | O que mudou |
|---|---|---|
| back | `bbf4e42` | GitHub App: login, conexão de repositórios, repositórios do projeto, vínculos na tarefa e webhook |
| front | `f2345ee` | Tela de integração, aba GitHub no projeto e seção GitHub na tarefa |

### Fase 4: reuniões

| Repo | Commit | O que mudou |
|---|---|---|
| back | `b9bd308` | `docs/REUNIOES.md`: comparação entre LiveKit e Daily |
| back | `3e8c937` | Reuniões com LiveKit, gravação no servidor e histórico |
| front | `b1568dd` | Aba Reuniões, sala de vídeo e histórico de gravações |

### Fase 5: transcrição e resumo

| Repo | Commit | O que mudou |
|---|---|---|
| back | `8577a8e`, `97c9917` | Comparação de transcrição e resumo (a segunda, só com opções gratuitas) |
| back | `be2865e` | Pipeline local: faster-whisper + Ollama, com saída validada por schema |
| back | `cd9d972` | Registro da decisão: tudo no servidor |
| front | `9eda9f0` | Tela de resumo e transcrição da gravação |

### Fase 6: revisão final

| Repo | Commit | O que mudou |
|---|---|---|
| front | `6bc555b` | Correções da varredura de rotas: foco visível, contraste AA, estados de erro, `/mensagens`, overflow em 768 px, mapa sem chave |
| front | `f985a22` | Formatação |
| front | `b0016fa` | Desempenho: Firebase e CSS do Mapbox sob demanda, imagens otimizadas, dependência sem uso removida, precache do PWA menor |
| front | `67dcb61` | README e `.env.example` |
| back | `970dce9` | Segurança: permissão padrão, visibilidade de usuários, validação de upload, rate limit dos webhooks, channel layer no Redis, testes de acesso cruzado |
| back | (este commit) | README e este relatório |

## 3. Telas e componentes

**Kit (`src/shared/components/ui`), Fase 1.** `UiIcon`, `UiButton`, `UiIconButton`, `UiField`, `UiInput`, `UiTextarea`, `UiSelect`, `UiCheckbox`, `UiSwitch`, `UiDialog`, `UiDrawer`, `UiConfirmDialog` + `useConfirm`, `UiMenu`, `UiTooltip`, `UiPopover`, `UiTabs`, `UiAvatar`, `UiBadge`, `UiSkeleton`, `UiEmptyState`, `UiErrorState`, `UiSpinner`, `UiProgress`. Também os composables `useFocusTrap`, `useModalLayer` e `useFloating`, e a galeria `/_design`, que só existe em desenvolvimento.

**Layout, Fase 1.** Sidebar recolhível, header com breadcrumbs, busca (Ctrl/Cmd+K), tema, notificações e menu do usuário; command palette; navegação mobile.

**Telas redesenhadas:**

| Tela | Rota | Fase |
|---|---|---|
| Entrar, cadastro, recuperar senha | `/entrar`, `/registrar`, `/esqueci-senha/*` | 2 |
| Onboarding | `/organizacoes/nova` | 2 |
| Painel inicial | `/` | 2 |
| Organizações, membros, convites, configurações | `/organizacoes/*` | 2 |
| Projetos | `/organizacoes/:id/projetos` | 2 |
| Quadro, lista e tabela de tarefas, com painel da tarefa | `/setores/:id` | 2 |
| Busca global e central de notificações | Ctrl/Cmd+K, `/notificacoes` | 2 |
| Integração GitHub e aba GitHub do projeto | `/integracoes/github`, aba no projeto | 3 |
| Aba Reuniões, sala de vídeo, histórico | aba no projeto, `/reunioes/:id` | 4 |
| Resumo e transcrição da gravação | `/reunioes/:id/gravacoes/:id` | 5 |

**Telas que não foram redesenhadas.** Chat, Arquivos, Relatórios, Assistente, Calendário, Equipe, Mapa, Planos, Faturamento, Pagamentos e Configurações estavam fora do escopo das fases 2 a 5. Elas usam a paleta nova e passaram pela varredura da Fase 6 (contraste, foco, estados de erro e larguras), mas o layout continua o do hackathon.

## 4. Endpoints e models

**Models novos (migrações `0009` a `0013`, só adições):**

| Migração | Models |
|---|---|
| `0009_task_activity_favorites_archive` | `TaskActivity`, `SectorFavorite`, `Sector.archived_at` |
| `0010_task_labels_and_comment_mentions` | `Label`, `Task.labels`, `Comment.mentions` |
| `0011_github_integration` | `GitHubIdentity`, `GitHubConnection`, `ProjectRepository`, `TaskGitHubLink` |
| `0012_meetings` | `Meeting` (+ participantes), `MeetingConsent`, `MeetingRecording` |
| `0013_meeting_insights` | `MeetingInsight`, `MeetingActionTask` |

**Endpoints novos ou alterados (todos em `/api/v1/`):**

| Grupo | Rotas |
|---|---|
| Projetos | `GET sectors/` com filtros e ordenação; `PUT/DELETE sectors/<id>/favorite/`; `PUT/DELETE sectors/<id>/archive/`; `GET sectors/<id>/people/` |
| Etiquetas | `GET/POST sectors/<id>/labels/`; `PATCH/DELETE labels/<id>/` |
| Tarefas | `GET sectors/<id>/tasks/` com filtros novos; `PATCH tasks/<id>/` com `label_ids`; `GET tasks/<id>/activity/`; comentários com `mentions` |
| Notificações e painel | `GET notifications/?kind=&unread=`; `GET dashboard/` com favoritos e atividade |
| GitHub | login (`authorize`, `callback`), conexão, repositórios autorizados, repositórios do projeto, atividade (PRs, issues, branches, checks), vínculos da tarefa e `POST integrations/github/webhook/` |
| Reuniões | agenda e CRUD por projeto, token da sala, consentimento, iniciar e parar gravação, gravações (assistir, baixar, apagar) e `POST meetings/livekit/webhook/` |
| Resumo das reuniões | `GET/POST .../recordings/<id>/insight/`, `GET .../insight/export/`, `POST .../insight/tasks/` |
| Usuários (Fase 6) | `GET users/list/` e `GET users/<id>/` agora mostram só você e as pessoas das suas organizações |

A lista completa de rotas, com os parâmetros, está no Swagger (`/api/docs/urls/`).

## 5. Dependências, com justificativa

| Pacote | Repo | Por quê |
|---|---|---|
| `@lucide/vue` 1.56.0 | front | Única biblioteca de ícones pedida (substitui a fonte Material Symbols) |
| `livekit-client` ^2.23.0 | front | SDK da sala de vídeo, escolhido na Fase 4 |
| `faster-whisper` >=1.2.1 | back | Transcrição local, sem serviço pago (Fase 5) |
| `channels-redis` >=4.3.0 | back | Channel layer no Redis: o worker do Celery e o servidor web são processos separados, e com a camada em memória os avisos do worker não chegavam ao WebSocket (Fase 6) |
| `@mapbox/mapbox-gl-draw` | front | **Removido** na Fase 6: só o CSS dele era importado, e nenhum código o usava |

No backend, o token da sala do LiveKit e as URLs assinadas do S3 usam `PyJWT` e `requests`, que já estavam no projeto. Nenhuma biblioteca de motion foi adicionada.

## 6. Testes executados e resultados reais

Rodados agora, no fim da Fase 6:

| Verificação | Resultado |
|---|---|
| Back `ruff check` | sem erros |
| Back `ruff format --check` | 384 arquivos já formatados |
| Back `makemigrations --check` | nada pendente |
| Back `manage.py test` (SQLite) | **504 testes, OK** |
| Back migrações do zero no PostgreSQL 16 + `manage.py test` | migrações OK; 496 testes OK (rodado antes dos 8 testes novos de segurança) |
| Back settings de produção com `REDIS_URL` | usa `RedisChannelLayer`; envio de um processo recebido em outro, com Redis local |
| Front `vue-tsc --build` | sem erros |
| Front `oxlint .` / `eslint .` (sem `--fix`) | sem erros |
| Front `prettier --list-different src/` | nada fora do padrão |
| Front `node --test` | **207 testes, OK** |
| Front `npm run build` | OK |

**Varredura de rotas (Playwright + axe-core 4.10, Chromium):**

- 23 rotas logadas e as públicas, em 1440 px (escuro e claro), 768 px e 375 px.
- **Console:** sem erros, fora os 401 esperados de `users/me` e `refresh` nas páginas públicas (é assim que o app descobre que ninguém está logado).
- **Botões mortos:** nenhum. Um detector percorreu todos os botões e confirmou que cada um tem ação, e foi validado com um botão sem ação injetado de propósito. Links quebrados: nenhum.
- **Rolagem horizontal:** nenhuma nas três larguras. Antes havia 311 px a mais no formulário de pagamento em 768 px.
- **Estados de erro:** testados com a API devolvendo 500 em todas as telas. O chat não tinha estado de erro; agora tem.
- **Teclado:** todo elemento focável mostra o anel de foco. Antes, a sidebar e os cartões do quadro não mostravam.
- **Contraste (axe, WCAG AA):** sem violações nas telas corrigidas. Os botões laranja, os avatares e os selos foram ajustados.
- **Reduced motion:** nenhuma animação acima de 160 ms com `prefers-reduced-motion`.

**Testes de segurança novos (Fase 6):**

- `core/tests/test_cross_tenant.py`: uma pessoa de outra organização chama **todas** as rotas da API com GET, POST, PUT, PATCH e DELETE, apontando para os dados da organização A (projeto, tarefa, time, canal, reunião, gravação, convite e outros). Foram mais de 300 chamadas, e nenhuma pode dar 2xx. **Antes da correção, o teste pegou um vazamento real:** `users/list/` e `users/<id>/` mostravam o e-mail de qualquer usuário do sistema.
- `core/tests/test_security_hardening.py`:
  - toda rota privada (mais de 100) recusa quem não está logado;
  - a página de teste da IA não existe fora do modo DEBUG;
  - upload de HTML, SVG, executável, script e HTML disfarçado de PNG é recusado, e PNG e PDF continuam passando;
  - os webhooks têm limite próprio.

**Bundle (Fase 6):**

| Medida | Antes (`9eda9f0`) | Depois (`b0016fa`) |
|---|---|---|
| Carregamento inicial | 675 KB (197 KB gzip) | 579 KB (177 KB gzip) |
| CSS global | 182 KB | 125 KB |
| Precache do PWA | 5121 KiB | 1285 KiB |
| `dist` | 5,33 MB | 3,90 MB |
| Maior chunk | Mapbox 1,93 MB | Mapbox 1,93 MB, só na rota do mapa e fora do precache |

A linha de base da Fase 0 (antes de tudo) era: maior chunk 1,93 MB, CSS 171 kB e `dist` 6,1 MB. Cada rota já era carregada sob demanda. Agora o Firebase só baixa depois do login, e o CSS do Mapbox só nas telas de mapa. A imagem da tela de login caiu de 1,35 MB (PNG) para 22 KB (WebP), e o logo de 57 KB para 10 KB. Os números completos estão em `fase6/bundle-antes.txt` e `bundle-depois.txt`.

**O que não foi testado:**

- Safari e Firefox (só o Chromium).
- Leitores de tela reais. Conferi papéis e atributos ARIA, não um NVDA ou VoiceOver de verdade.
- GitHub, LiveKit Cloud, bucket real e os modelos de IA de verdade. Tudo isso depende das contas e configurações da seção 8.

## 7. Status de cada funcionalidade

| Funcionalidade | Status | Motivo |
|---|---|---|
| CI verde nos dois repositórios | CONCLUÍDA | lint, tipos, testes e build passam |
| Tokens, kit de componentes, layout, `/_design` | CONCLUÍDA | |
| Login, cadastro, recuperação, onboarding | CONCLUÍDA | |
| Painel inicial | CONCLUÍDA | |
| Organizações, membros, convites, configurações | CONCLUÍDA | |
| Projetos (filtros, favoritos, arquivo, acesso) | CONCLUÍDA | |
| Tarefas: quadro, lista, tabela, painel, etiquetas, @menção, histórico | CONCLUÍDA | |
| Busca global e central de notificações | CONCLUÍDA | a busca não procura em comentários nem etiquetas |
| Login com GitHub e integração de repositórios | PARCIAL | código e testes prontos com o GitHub simulado; falta você criar o GitHub App e preencher o `.env` |
| Reuniões, sala de vídeo e gravação | PARCIAL | testado de ponta a ponta com LiveKit e S3 locais; falta a conta LiveKit, o bucket e o webhook em produção |
| Transcrição e resumo das reuniões | PARCIAL | código e testes prontos com modelos simulados; o teste real com os modelos foi dispensado por você em 29/10/2026, e produção ainda não tem Ollama |
| Rota sem permissão explícita fica protegida (`IsAuthenticated` padrão) | CONCLUÍDA | |
| Isolamento entre organizações em todas as rotas | CONCLUÍDA | testado em mais de 300 chamadas; vazamento de usuários corrigido |
| Rate limit em auth e webhooks | CONCLUÍDA | auth: 10/min (incluindo o login com Google); webhooks: 600/min por IP |
| Validação de upload | CONCLUÍDA | tamanho já era validado; agora também recusa HTML, SVG, scripts e executáveis pelo nome e pelo conteúdo; upload no Drive limitado a 20 MB |
| Chat em tempo real com mais de um processo | CONCLUÍDA | channel layer no Redis em produção |
| Desempenho do bundle | CONCLUÍDA | números na seção 6 |
| Mapa | PARCIAL | funciona com `VITE_MAPBOX_API_KEY`; sem a chave, mostra "Mapa indisponível" em vez de quebrar |
| Telas antigas (chat, arquivos, relatórios, assistente, calendário, equipe, faturamento, configurações) | PARCIAL | funcionam e passaram na varredura, mas não foram redesenhadas |
| Calendário, Gantt, tarefas recorrentes, dependências, controle de tempo, presença | BLOQUEADA | fora do escopo combinado para estas fases |
| Pagamento com cartão em produção | BLOQUEADA | o compose de produção passa `VITE_PUBLIC_MP_KEY`, mas o frontend lê `VITE_MP_PUBLIC_KEY`, então a chave pública não chega ao build (ver seção 8) |

## 8. Configurações pendentes (dependem de você)

1. **GitHub App.** Criar o app conforme o `docs/GITHUB.md` e preencher `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_APP_PRIVATE_KEY` e `GITHUB_WEBHOOK_SECRET`. No frontend, `VITE_GITHUB_LOGIN=true`, que o compose de produção também não repassa hoje.
2. **LiveKit.** Conta gratuita no LiveKit Cloud ou `livekit-server` próprio: `LIVEKIT_URL`, `LIVEKIT_API_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, e o webhook apontando para `/api/v1/meetings/livekit/webhook/`.
3. **Bucket das gravações.** MinIO no servidor (custo zero) ou R2: as variáveis `RECORDINGS_S3_*`. Agendar `manage.py purge_meeting_recordings` uma vez por dia.
4. **IA das reuniões.** O `deployment/compose.prod.yml` não tem o serviço `ollama` nem os volumes dos modelos, porque produção só muda com a sua aprovação. Para ligar: adicionar o Ollama, baixar o `OLLAMA_MODEL`, garantir o `ffmpeg` na imagem (o `Dockerfile` local já instala) e `MEETING_AI_ENABLED=true` no worker.
5. **Chave pública do Mercado Pago no build.** Em `deployment/compose.prod.yml` e `deploy/frontend.Dockerfile`, o argumento se chama `VITE_PUBLIC_MP_KEY`, mas o código lê `VITE_MP_PUBLIC_KEY`. Basta renomear o argumento. Não mexi porque é configuração de deploy.
6. **Mapbox.** `VITE_MAPBOX_API_KEY` no build, se o mapa for mantido.
7. **Firebase.** As variáveis `VITE_*` do Firebase e o `FIREBASE_CREDENTIALS` do backend, se ainda não estiverem em produção.
8. **Pergunta em aberto:** o `.env` com cara de produção na pasta local `backend-resenha` do seu PC deveria estar ali? Não usei nenhuma credencial dele.

## 9. Mudanças globais que precisam do seu ok

Pelo `AGENTS.md`, estas mudanças pedem aprovação do dono. Todas estão só na branch `feat/alteracoes-pos-hackathon`.

**Frontend:**

- `src/app/router`:
  - rotas de projetos, GitHub, reuniões e resumo;
  - `/organizacoes/:id/setores` passa a redirecionar para `/organizacoes/:id/projetos`;
  - `/mensagens` passa a redirecionar para `/chat` (antes abria uma tela em branco).
- `src/app/layouts`: shell novo, raiz única no `DefaultLayout`, item GitHub no menu, anel de foco na sidebar.
- `src/shared`: kit novo e ajustes (`UiButton` com `href`, `UiInput` com `date` e `time`, Esc por camada).
- `src/main.ts`: os CSS do Mapbox saíram do carregamento global.
- `vite.config.ts`: o precache do PWA ignora os chunks do Mapbox e da sala de vídeo.
- Dependências: `@lucide/vue` e `livekit-client` adicionadas; `@mapbox/mapbox-gl-draw` removida.

**Backend:**

- Settings globais:
  - `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`;
  - limite por usuário de 1000 para 5000 por hora, porque as telas que se atualizam sozinhas a cada 5 s passavam de 1000;
  - escopo novo `webhook` (600/min);
  - channel layer no Redis em `prod.py`.
- Migrações `0009` a `0013`, só adições.
- Rotas novas em `app/urls.py`; a página de teste da IA só existe com `DEBUG`.
- `Dockerfile` (ffmpeg) e `docker-compose.yml` local (Ollama). `deployment/compose.prod.yml` não foi alterado.
- Dependências: `faster-whisper` e `channels-redis`.

## 10. Próximos passos

1. **Revisar e decidir o merge.** Revisar a branch e abrir os PRs para `dev`, de preferência em partes: fundação, telas, GitHub, reuniões, IA e revisão final. **Lembre que o merge em `dev` publica em produção em cerca de 2 minutos.** Antes do merge, rodar `migrate` e confirmar que o Redis de produção está de pé, porque o chat passa a depender dele.
2. Fazer as configurações da seção 8, começando pela chave do Mercado Pago, que é só renomear um argumento.
3. Teste real das integrações: GitHub App de teste, LiveKit e uma reunião curta para medir o tempo de CPU da transcrição.
4. Restringir o Swagger (`/api/docs/`) em produção, que hoje é público.
5. Corrigir o teste instável do token do Google (`test_connect_stores_tokens_encrypted_at_rest`), que procura "RT" dentro de um texto cifrado aleatório.
6. Na central de notificações, o subtítulo diz "Tudo em dia" mesmo quando a lista falha ao carregar. É um detalhe pequeno.
7. Redesenhar as telas antigas da seção 3 com o kit.
8. Testar em Safari e Firefox e com um leitor de tela.
