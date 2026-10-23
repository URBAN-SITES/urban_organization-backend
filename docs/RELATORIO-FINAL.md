# Relatório final: Hackathon 3INFO

Organização colaborativa de projetos e tarefas (Kanban genérico e adaptável)

IFC Campus Araquari, 23 e 24 de outubro de 2026, das 08h às 08h (24 horas).

Este relatório sintetiza o objetivo, as funcionalidades, o modelo de dados e as decisões do projeto. Ele acompanha dois arquivos: `modelagem-final.sql` (PostgreSQL, com flags de prioridade) e `modelagem-final.dbml` (diagrama para o dbdiagram.io).

---

## 1. Objetivo

Entregar uma aplicação em que equipes organizam e acompanham projetos e tarefas de forma colaborativa, com uma visão clara de quem faz o quê, o que está atrasado e quanto do trabalho já foi concluído.

O desafio pede um quadro inspirado em Kanban, que sirva a qualquer contexto (feira escolar, trabalho em grupo, campanha solidária, evento), sem ficar preso a projetos de software.

**Conceito do produto:** um "GitHub Projects" genérico e adaptável.

```
Usuário → Organização → Setor (onde vive o quadro Kanban) → Tarefa
```

- **Organização:** o espaço de trabalho. Todo usuário ganha uma organização pessoal ao se cadastrar, então não existe caso especial para "projeto fora de empresa".
- **Setor:** é o "projeto" do enunciado. Tem participantes, status próprios (colunas livres) e as tarefas.
- **Tarefa:** título, descrição, prioridade, prazo, responsável, checklist, comentários e links.

**O que o enunciado avalia:** os requisitos básicos funcionando com dados criados durante o uso, mais, no mínimo, uma integração que faça uma operação efetiva com um serviço externo. Colar um link manualmente não conta como integração.

---

## 2. Prioridades (as flags)

Todo o código está marcado com três níveis. O mesmo código de cor está no DBML (cabeçalho verde, roxo, cinza) e nos comentários do SQL.

| Flag | Significado | Regra |
|---|---|---|
| **P1** | Fundamental: requisito obrigatório ou base de tudo | Implementar primeiro. Nunca depende de P2 ou P3. |
| **P2-A..I** | Secundário: diferencial | Só depois do P1 estável. Cada bloco é independente e removível (exceto onde indicado). |
| **P3** | Só schema | Modelo pronto para escalar, sem implementação prevista. |

### P1: fundamental (10 tabelas)

| Requisito do desafio | Tabelas |
|---|---|
| Identificar usuários e controlar o acesso | `users`, `organization_members`, `sector_members` |
| Gerenciar projetos e participantes | `organizations`, `sectors`, `sector_members` |
| Gerenciar tarefas (título, descrição, prioridade, prazo, responsável) | `tasks` |
| Quadro Kanban com no mínimo 3 situações | `statuses` (criados por padrão: A fazer, Em andamento, Concluído) |
| Checklist e comentários com autor | `checklist_items`, `comments` |
| Prazos vencidos, data de conclusão e progresso | `tasks.completed_at`, views `overdue_tasks` e `sector_progress` |
| Materiais de apoio (links) | `resource_links` |
| Persistência dos dados | PostgreSQL |

Busca por título e filtros (responsável, situação, prioridade, prazo) não precisam de tabela: são consultas sobre `tasks`.

### P2: secundário (19 tabelas, 9 blocos)

| Bloco | Funcionalidade | Tabelas | Depende de |
|---|---|---|---|
| P2-A | Times (um nível, sem sub-times) | `teams`, `team_members`, `sector_teams` | n/d |
| P2-B | Login com Google (OAuth) | `user_identities` | n/d |
| P2-C | Preferências do usuário (tema, toggles de notificação) | `user_settings` | n/d |
| P2-D | Convites por e-mail e contagem de e-mails | `organization_invites`, `email_log` | n/d |
| P2-E | Notificações no app e push | `notifications`, `push_subscriptions` | n/d |
| P2-F | Google Agenda | `user_integrations`, `task_calendar_events` | n/d |
| P2-G | Plano pago (assinatura e pagamento) | `plans`, `subscriptions`, `payments`, `payment_events` | n/d |
| P2-H | Chat (organização, time e direto) | `chat_channels`, `chat_channel_members`, `chat_messages` | P2-A |
| P2-I | Anexos (upload de documentos) | `attachments` | `message_id` usa P2-H |

### P3: só schema (5 tabelas)

`custom_fields`, `custom_field_options`, `task_field_values`, `views`, `task_dependencies`. Dão o "adaptável" do GitHub Projects (campos por setor, visões salvas, dependências), mas custam muito de tela e de consulta.

---

## 3. Modelo de dados: regras que importam

### Acesso a um setor

A pergunta "esta pessoa pode ver este setor, e com qual papel?" tem uma resposta só, na view `sector_effective_members`. O papel efetivo é o **maior** entre:

1. participante direto do setor (`sector_members`);
2. membro de um time vinculado ao setor (`sector_teams`), só com P2-A;
3. owner ou admin da organização (manager implícito);
4. qualquer membro da organização, como viewer, se o setor **não** for privado.

`is_private` é `true` por padrão, o que atende "somente os participantes de um projeto consultam e alteram".

**Usuário ou time tem permissão?** Os dois, com papéis diferentes. O usuário tem o papel base (na organização e no setor). O time não tem permissões próprias: ele só carrega um papel de setor para todos os seus membros. Não há regras de negação, só soma.

### Quadro Kanban

- Cada setor define seus status. O campo `statuses.category` (`todo`, `in_progress`, `done`) dá o significado, então os nomes são livres ("Em revisão", "Aprovado") e o sistema ainda sabe quando algo está concluído.
- `tasks.completed_at` é preenchido ao entrar num status `done` e limpo ao sair.
- **Atraso:** `due_date < hoje` e `completed_at` nulo (view `overdue_tasks`).
- **Progresso:** tarefas com `completed_at` ÷ total do setor (view `sector_progress`).

### Premium (P2-G)

O premium é do **usuário**. A regra está na função `is_premium(user_id)`: tem acesso quem possui assinatura `trialing` ou `active`, ou `canceled` ainda dentro do período pago (`current_period_end` no futuro). `past_due`, `expired` e `incomplete` não têm acesso. A view `user_premium_status` traz plano e data de expiração. A tabela `payment_events` guarda os webhooks do gateway, e a restrição de unicidade impede processar o mesmo evento duas vezes.

Se depois quiserem que o premium valha para a organização inteira, troque `user_id` por `organization_id` em `subscriptions`.

### Outras decisões

| Decisão | Motivo |
|---|---|
| Organização pessoal automática | Um fluxo único, sem caso especial para projeto pessoal |
| Setor = projeto do desafio | Mapeia direto os requisitos; `sector_members` vira a lista de participantes |
| Papéis em enums fixos (`org_role`, `sector_role`, `team_role`) | Mais rápido que tabela `roles` com permissões personalizáveis |
| Times com um nível | Decisão da equipe: sem "times de times" |
| `status_id` com FK composta `(status_id, sector_id)` | Impede mover tarefa para status de outro setor |
| Tokens do Google guardados criptografados (`*_enc`) | Segurança básica de credenciais |

---

## 4. Plano de implementação em Django

A base do projeto será Django. Eu **não vi** a documentação existente da base, então esta seção descreve o mapeamento técnico para vocês encaixarem nas convenções que já têm.

### Papel de cada arquivo

O SQL é a **especificação de referência**. Com Django, quem cria o banco são as migrations dos models. Isso muda três coisas:

- Os enums do SQL viram `TextChoices` nos models (o Django guarda como texto).
- Os triggers e as views do SQL precisam virar código Django (ou `RunSQL` nas migrations).
- Algumas restrições têm tradução direta e outras não.

### Apps sugeridos (espelham as flags)

| Prioridade | App | Models |
|---|---|---|
| P1 | `accounts` | `User` |
| P1 | `organizations` | `Organization`, `OrganizationMember` |
| P1 | `kanban` | `Sector`, `SectorMember`, `Status`, `Task`, `ChecklistItem`, `Comment`, `ResourceLink` |
| P2 | `teams`, `invitations`, `notifications`, `calendar_sync`, `billing`, `chat`, `attachments` | um app por bloco P2 |
| P3 | (adiar) | campos personalizados, visões, dependências |

Sugestão de uso das flags no código: um comentário `# [P1]` ou `# [P2-G]` no topo de cada model, e um dicionário `FEATURES` em `settings.py` para esconder da interface o que ainda não foi implementado.

### Tradução das regras do SQL

| No SQL | Em Django |
|---|---|
| Usuário com e-mail único sem diferenciar maiúsculas | `UniqueConstraint(Lower("email"), ...)` |
| `password_hash` nulo (só Google) | Usar o campo `password` do Django e `set_unusable_password()` |
| Índice parcial (convite pendente, assinatura viva) | `UniqueConstraint(..., condition=Q(...))` |
| `CHECK` de "exatamente um destino" (`resource_links`) | `CheckConstraint` com `Q` |
| Triggers (setor padrão, dono da organização, `completed_at`) | Funções de serviço dentro de `transaction.atomic`, ou signals |
| Views (`sector_progress`, `overdue_tasks`, `sector_effective_members`) | Métodos de manager/queryset (`annotate`, `filter`) |
| Função `is_premium` | Propriedade/método que consulta `Subscription` com a mesma regra |
| FK composta `(status_id, sector_id)` | Ver atenção abaixo |

### Pontos de atenção

1. **Modelo de usuário customizado antes da primeira migration.** `AUTH_USER_MODEL` não se troca depois sem dor. Definam o `User` com login por e-mail e chave primária UUID desde o início.
2. **FK composta.** Até onde sei, o Django não tem chave estrangeira composta nativa (confirmem na versão que usarem). Validem no serviço ou em `clean()` que o status pertence ao setor da tarefa; se quiserem a garantia no banco, uma migration `RunSQL` com a constraint do SQL resolve.
3. **Signals não rodam em operações em lote** (`bulk_create`, `update`). Por isso a regra do `completed_at` deve ficar numa função única, usada em todo lugar que move tarefa.
4. **Login com Google.** Se adotarem uma biblioteca de autenticação social (a `django-allauth` é a opção comum), ela traz suas próprias tabelas de contas sociais e tokens. Nesse caso `user_identities` e parte de `user_integrations` deixam de ser necessárias. Decidam isso antes de criar os models do P2-B.
5. **Chat em tempo real** exige ASGI e algo como Django Channels. É a maior infraestrutura extra do projeto.
6. **Push** precisa de service worker, HTTPS e chaves VAPID.
7. **Webhook de pagamento:** endpoint sem CSRF, com verificação de assinatura do gateway e gravação em `payment_events` antes de processar.
8. **Upload:** o `FileField` e um storage resolvem; limitem tamanho e tipo, e limpem arquivos órfãos ao apagar o registro.
9. **Fuso horário:** `USE_TZ = True` e `TIME_ZONE = "America/Sao_Paulo"`. O SQL usa `timestamptz` para isso.

---

## 5. Riscos e complexidade

Do mais arriscado para o menos, considerando 24 horas e o que o desafio avalia.

1. **Chat:** o modelo é simples, mas o chat de verdade custa tempo (tempo real, não lidas, reconexão).
2. **Pagamento e assinatura:** o difícil é o fluxo (checkout, webhook, estados, sandbox), não as tabelas.
3. **Push:** service worker, permissão do navegador, chaves. As notificações dentro do app já entregam o valor.
4. **Duas integrações Google** (login e Agenda): o login é fácil; a Agenda exige consentimento, refresh token e sincronização. Mantenham a sincronização num sentido só: criar ou atualizar o evento quando o prazo muda.
5. **Convites por e-mail:** precisam de provedor de e-mail, token e expiração.
6. **Anexos:** upload seguro, limites e storage.
7. **Campos personalizados e visões (P3):** o que mais custa de tela e de consulta, e o que menos aparece na demonstração.
8. **Acesso ao setor por quatro caminhos** e papéis em três níveis: corretos, mas difíceis de explicar e testar.
9. **Triggers no SQL:** ao portar para Django viram código de serviço; vale testar cada um.

**Cortes mais seguros, nesta ordem:** campos personalizados e visões, chat em tempo real (ou só o canal da organização), push.

**Estratégia recomendada:** o núcleo P1 mais **uma** integração bem feita (Google Agenda **ou** pagamento em sandbox) cumpre o que o desafio pede. Uma integração funcionando vale mais que cinco pela metade.

---

## 6. Cronograma sugerido (24 horas)

| Janela | Entrega |
|---|---|
| Até ~12h | Projeto Django criado, `User` customizado, autenticação, organização e setor |
| 12h às 18h | Quadro Kanban com mover cards, tarefas, checklist, comentários e links |
| 18h às 22h | Busca e filtros, atrasadas, progresso, permissões, conferir persistência |
| 22h às 03h | A integração escolhida; times se sobrar tempo |
| 03h às 06h | Dados de demonstração e teste do fluxo completo |
| 06h às 08h | Ensaio da apresentação, sem funcionalidade nova |

Congelar funcionalidades novas às 06h.

---

## 7. Decisões em aberto

| # | Decisão | Impacto |
|---|---|---|
| 1 | **Qual integração será a "efetiva"?** Google Agenda ou pagamento em sandbox | Define onde vai o tempo da madrugada |
| 2 | **Gateway de pagamento** (Stripe, Mercado Pago, Asaas...) | O modelo é genérico, mas o fluxo de webhook muda |
| 3 | **Login Google com biblioteca pronta ou à mão** | Define se `user_identities` existe no Django |
| 4 | **"Traduzir e anexar documentos"** | Interpretei como enviar e anexar arquivos. Se for traduzir o conteúdo, é outra funcionalidade (API externa) e não está modelada |
| 5 | **Papéis personalizados por organização** | Hoje são enums fixos; a tela de referência sugere papéis nomeados por domínio |
| 6 | **Tamanho da equipe e divisão de tarefas** | Define quantos blocos P2 cabem |

---

## 8. Como usar este relatório para atualizar a documentação

Seções da documentação que provavelmente mudam (vale conferir contra a documentação atual):

- **Visão geral e escopo:** seções 1 e 2 deste relatório.
- **Prioridades e entrega:** a tabela de flags (seção 2) e o cronograma (seção 6).
- **Estrutura de apps:** a tabela de apps sugeridos (seção 4).
- **Convenções de models:** UUID, `TextChoices`, flags `# [P1]`, `FEATURES` em `settings.py`.
- **Modelo de dados e regras de negócio:** seção 3.
- **Permissões:** a regra de acesso ao setor (seção 3).

---

## Apêndice: validação

O arquivo `modelagem-final.sql` foi executado inteiro num PostgreSQL 16 em banco vazio, sem erros, e um teste de fumaça confirmou: criação das 34 tabelas; organização pessoal e vínculo de owner ao cadastrar usuário; status padrão e manager ao criar setor; canal de chat da organização e do time; `completed_at` preenchido e limpo ao mover a tarefa; progresso de 100%; tarefas atrasadas; acesso ao setor via time com papel `editor`; `is_premium` nos quatro estados (sem assinatura, ativa, cancelada dentro do período, expirada); bloqueio de status de outro setor pela FK composta; e bloqueio de convite pendente duplicado.

O `modelagem-final.dbml` **não** foi aberto no dbdiagram.io (o recurso de cor de cabeçalho e os grupos de tabela usam a sintaxe padrão do DBML, mas confirmem ao colar).
