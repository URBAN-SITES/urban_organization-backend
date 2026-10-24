# Implementação de criação e gerenciamento de Tasks com Gemini — Django REST Framework

## Objetivo

Implemente no backend Django REST Framework existente uma funcionalidade que permita ao usuário criar, consultar e editar Tasks por meio de solicitações em linguagem natural ao chatbot integrado com a API do Google Gemini.

A integração com o Gemini e o chatbot já existem e devem ser preservados. O objetivo é ampliar suas funcionalidades por meio de **Function Calling**, permitindo que a IA solicite operações no sistema, sem acessar diretamente o banco de dados.

## 1. Análise inicial do projeto

Antes de escrever código:

- Inspecione a organização atual do backend, identificando Views, Serializers, Services e Models.
- Identifique como o chatbot e a API do Gemini estão implementados.
- Analise a Model de Tasks, seus relacionamentos, campos e regras de negócio.
- Identifique os Services e Serializers já responsáveis pela criação e edição de Tasks.
- Verifique como funcionam autenticação, permissões e identificação do usuário.
- Reutilize os padrões existentes, evitando duplicações e refatorações desnecessárias.

## 2. Arquitetura obrigatória

Respeite as responsabilidades das camadas já existentes:

- **View:** recebe a mensagem do usuário autenticado e retorna a resposta do chatbot.
- **Serializer:** valida os dados necessários às operações de Tasks.
- **ChatService:** orquestra a comunicação com o Gemini, identifica solicitações de ferramentas e encaminha sua execução.
- **Gemini Client:** disponibiliza ao modelo as ferramentas autorizadas por meio de Function Calling.
- **TaskService:** executa consultas, criações e alterações utilizando o Django ORM e as regras de negócio existentes.
- **Model:** mantém as restrições e a estrutura dos registros.

Não introduza novas camadas arquiteturais desnecessárias. Adapte a implementação à estrutura atual do projeto.

## 3. Function Calling com Gemini

Utilize os recursos de Function Calling do SDK oficial do Gemini já configurado.

Disponibilize inicialmente as seguintes ferramentas:

- `listar_tasks`: consultar as Tasks pertencentes ao usuário.
- `buscar_task`: localizar uma Task específica por identificador ou características.
- `criar_task`: criar uma Task a partir das informações fornecidas pelo usuário.
- `editar_task`: atualizar campos de uma Task existente.
- `concluir_task`: marcar uma Task como concluída, caso essa operação seja compatível com a Model existente.

As ferramentas devem utilizar os campos e as regras reais da aplicação, sem presumir nomes ou estruturas.

O Gemini deve interpretar a solicitação e retornar o nome da ferramenta e seus argumentos. **A execução deve ser controlada pelo Django**, que validará os dados antes de chamar os Services correspondentes.

Não permita execução arbitrária de métodos, consultas SQL geradas pela IA ou acesso direto do Gemini ao banco.

## 4. Criação de Tasks

O chatbot deve reconhecer solicitações como:

"Crie uma tarefa para estudar Django amanhã, com prioridade alta."

Ao identificar uma solicitação de criação:

1. Extrair as informações fornecidas pelo usuário.
2. Identificar os campos necessários segundo a Model existente.
3. Interpretar datas relativas considerando a data e o fuso horário do sistema.
4. Solicitar informações adicionais quando faltarem dados obrigatórios.
5. Validar os argumentos com os mecanismos existentes.
6. Executar a criação por meio do TaskService.
7. Retornar ao Gemini o resultado da operação.
8. Informar ao usuário se a Task foi criada com sucesso.

Não invente valores obrigatórios ausentes nem confirme operações antes de sua execução.

## 5. Consulta e edição de Tasks

O chatbot também deve compreender solicitações como:

- "Quais tarefas tenho para amanhã?"
- "Mostre minhas tarefas pendentes."
- "Altere a prioridade da tarefa de matemática para alta."
- "Marque a tarefa de estudar Django como concluída."

Para consultas, utilize os métodos existentes ou implemente métodos apropriados no TaskService.

Para edições:

1. Identificar a Task solicitada.
2. Verificar se pertence ao usuário autenticado.
3. Identificar os campos que devem ser modificados.
4. Validar os novos valores.
5. Aplicar as regras de negócio existentes.
6. Persistir as alterações.
7. Retornar o resultado ao chatbot.

Quando houver múltiplas Tasks correspondentes ou informações ambíguas, o chatbot deverá solicitar esclarecimento antes de executar a alteração.

Não implemente exclusão de Tasks nesta etapa.

## 6. Contexto da conversa

Preserve o funcionamento atual do histórico do chatbot.

O Gemini deve conseguir interpretar referências a mensagens anteriores, como:

"Crie uma tarefa para estudar Python amanhã."

"Agora altere a prioridade dela para alta."

Nesse exemplo, a segunda mensagem deve se referir à Task criada anteriormente.

Preserve no contexto os resultados relevantes das ferramentas executadas, especialmente os identificadores das Tasks.

Não utilize o histórico da conversa como substituto da verificação de permissões no backend.

## 7. Segurança e validação

- Todas as operações devem respeitar o usuário autenticado.
- O Gemini não deve acessar ou modificar Tasks de outros usuários.
- Utilize exclusivamente ferramentas explicitamente autorizadas.
- Reutilize os Serializers, Services e regras de negócio existentes.
- Não confie automaticamente nos argumentos gerados pelo modelo.
- Evite execuções duplicadas da mesma operação.
- Solicite confirmação quando uma alteração for ambígua ou potencialmente sensível.
- Trate falhas do Gemini, erros de validação e registros inexistentes.
- Não permita que instruções do usuário contornem as permissões do Django.

## 8. Integração com o chatbot existente

Integre as novas ferramentas ao fluxo atual do chatbot, sem criar outro chat ou outro endpoint desnecessariamente.

O fluxo esperado é:

1. O usuário envia uma mensagem.
2. O Gemini interpreta a solicitação.
3. Caso necessário, solicita a execução de uma ferramenta.
4. O ChatService valida e encaminha a operação ao TaskService.
5. O Django executa a operação e retorna seu resultado.
6. O resultado é enviado ao Gemini.
7. O chatbot responde ao usuário em linguagem natural.

Perguntas que não exigem operações sobre Tasks devem continuar funcionando normalmente.

## 9. Testes e entrega

Implemente testes para:

- Criação de Tasks por solicitações em linguagem natural.
- Consulta de Tasks do usuário autenticado.
- Edição e conclusão de Tasks.
- Referências a Tasks mencionadas anteriormente.
- Tratamento de solicitações ambíguas.
- Rejeição de argumentos inválidos.
- Impedimento de acesso a Tasks de outros usuários.
- Tratamento de falhas do Gemini.
- Preservação das funcionalidades existentes do chatbot.

Utilize mocks para evitar chamadas reais ao Gemini nos testes automatizados.

Ao finalizar, informe os arquivos criados ou modificados, explique brevemente as alterações e apresente exemplos de requisições para testar as funcionalidades.

**Restrições finais:**

- Não modificar o frontend.
- Não reimplementar o chatbot.
- Não modificar desnecessariamente as Models existentes.
- Não permitir acesso direto da IA ao banco.
- Não adicionar exclusão de Tasks.
- Priorizar a reutilização da arquitetura e das regras de negócio já implementadas.