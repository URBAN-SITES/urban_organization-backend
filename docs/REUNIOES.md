# Reuniões e gravação: comparação de provedores

Consulta feita em 29/10/2026 nas páginas oficiais listadas no fim. Os preços mudam:
confira de novo antes de contratar.

## O que precisamos

- sala de vídeo no navegador (Vue 3, sem React);
- gravação no servidor com indicador para todos;
- arquivo em storage com URL assinada;
- token da sala gerado sempre no backend Django;
- teste real local com duas abas.

## Comparação

| Critério | LiveKit Cloud | LiveKit self-hosted | Daily |
|---|---|---|---|
| Plano gratuito | Build, US$ 0: 5.000 participante-minutos, 50 GB de tráfego, 100 conexões simultâneas | Software livre (Apache 2.0). Paga só a máquina | 10.000 participante-minutos por mês |
| Gravação no servidor | Egress, já incluso. Build tem 60 min de transcodificação por mês e 2 gravações simultâneas | Egress em contêiner separado. Usa 4 CPUs e 4 GB por sala gravada ao mesmo tempo | Cloud recording **só em plano pago** |
| Limite do gratuito | Teto rígido: passando da cota, novas requisições falham e não há cobrança | Só o da máquina | Pay-as-you-go: passou de 10.000 min, cobra |
| Preço depois | Ship US$ 50/mês: 150.000 min, 600 min de gravação, excedente US$ 0,02/min de gravação e US$ 0,0005/min de participante | Custo da VPS mais o storage | US$ 0,004 por participante-minuto, gravação US$ 0,01349/min mais armazenamento US$ 0,003/min |
| Onde fica o arquivo | S3, GCS ou Azure (nosso bucket) | S3, GCS ou Azure (nosso bucket) | Bucket da Daily (link de 15 min a 12 h) ou nosso S3 (link de até 1 h) |
| Duração máxima da gravação | 3 h por arquivo MP4 | Configurável | 3 h |
| SDK frontend | `livekit-client` (JS puro, serve para Vue). Componentes prontos só para React | Igual | `@daily-co/daily-js` (JS puro, "call object"). Prebuilt em iframe |
| SDK backend | `livekit-api` (Python): token JWT assinado localmente, API de Egress e webhooks | Igual | REST: cria sala e token por HTTP |
| Teste local sem conta | **Sim**: `livekit-server --dev` mais o Egress em Docker | Sim | Não: toda sala fica na nuvem da Daily |
| Complexidade | Baixa | Alta: IP público, portas UDP, TLS e TURN, Redis, contêiner do Egress, monitoramento | Baixa |
| Trocar depois | Mesmo código do self-hosted | Mesmo código do Cloud | Reescrever tudo para sair |

### Custo estimado

Exemplo: 4 pessoas, 5 reuniões de 1 h por semana (cerca de 20 h por mês).

| Item | Quantidade |
|---|---|
| Participante-minutos | 4 × 60 × 20 = 4.800 |
| Minutos gravados, se gravar tudo | 1.200 |

- **LiveKit Cloud Build**:
  - os 4.800 participante-minutos cabem nos 5.000;
  - a gravação, não: só 60 min cabem;
  - gravar tudo exige o **Ship (US$ 50/mês)**, cujos 600 min incluídos mais 600 min de excedente a US$ 0,02 dão cerca de US$ 62 por mês.
- **Daily**:
  - os participante-minutos são grátis;
  - a gravação custa 1.200 × US$ 0,01349, cerca de US$ 16, mais o armazenamento;
  - precisa de cartão.
- **LiveKit self-hosted**:
  - não tem cobrança por minuto;
  - precisa de uma máquina com no mínimo 4 CPUs e 4 GB só para gravar uma sala por vez, além do servidor de mídia.
  - Não estimei o preço da VPS, porque depende do provedor que vocês usam.

Nos três casos falta o **storage** dos vídeos. O backend hoje grava arquivos em disco e usa o Cloudinary, e nenhum dos dois serve de saída do Egress. É preciso um bucket compatível com S3 (AWS S3, Cloudflare R2 ou outro). Não incluí o preço porque ainda não sei qual vocês preferem.

## Recomendação: LiveKit, começando pelo Cloud

1. **Dá para testar de verdade aqui, sem conta e sem custo.** O `livekit-server --dev` e o Egress em Docker permitem fazer o checkpoint com duas abas, inclusive a gravação, sem criar conta em nenhum serviço.
2. **Não prende.** O mesmo código serve para o LiveKit Cloud e para um servidor próprio. Dá para começar no Build gratuito e migrar se o custo crescer.
3. **O plano gratuito não gera cobrança surpresa.** Passou da cota, a sala falha em vez de cobrar.
4. **O token é JWT assinado no próprio Django** com a chave da API, sem chamada externa. Isso atende "o token da sala é gerado no backend, sempre".
5. A gravação vai para o **nosso bucket**, e o Django gera a URL assinada. Assim o controle de quem baixa fica com a gente.

**Contra:**

- No Build gratuito só cabem 60 min de gravação por mês. Para gravar de verdade, o Ship custa US$ 50 por mês.
- Não há componentes prontos para Vue. A sala será montada com o kit da Fase 1 sobre o `livekit-client`, o que também mantém o visual do Inceptum.

**Quando a Daily seria melhor:** se a prioridade for o menor custo de gravação em volume baixo, e vocês aceitarem cartão desde o início e não ter teste local. O preço por minuto gravado é menor, mas sair dela depois exige reescrever a integração.

## O que vou precisar depois da aprovação

| Item | Para o teste local | Para produção |
|---|---|---|
| Servidor de mídia | `livekit-server --dev` (binário oficial) | Conta LiveKit Cloud (você cria) ou servidor próprio |
| Gravação | Contêiner `livekit/egress` mais Redis local | Incluso no Cloud |
| Storage | MinIO local (compatível com S3) | Bucket S3 ou R2 (você escolhe e cria) |
| Dependências novas | Backend `livekit-api`; frontend `livekit-client` | Iguais |
| `.env` | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `RECORDINGS_S3_*` | Iguais, com valores reais |

As dependências novas e a criação de contas precisam da sua aprovação, conforme o AGENTS.md e as regras do plano.

## Fontes

- LiveKit, preços: https://livekit.com/pricing
- LiveKit, cotas e limites: https://docs.livekit.io/deploy/admin/quotas-and-limits/
- LiveKit, Egress self-hosted: https://docs.livekit.io/transport/self-hosting/egress/
- Daily, preços: https://www.daily.co/pricing/video-sdk/
- Daily, gravação: https://docs.daily.co/guides/products/live-streaming-recording/recording-calls-with-the-daily-api
- Daily, link de acesso da gravação: https://docs.daily.co/reference/rest-api/recordings/get-recording-link
