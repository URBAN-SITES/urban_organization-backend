# Template de Projeto Base para Django REST Framework

**Objetivo:** ...

## Estado atual

### URLs
- /api/users/

Requisição GET que retorna lista de todos os usuários no sistema. Apenas usuários authenticados tem permissão de fazer essa requisição. São filtrados da busca, usuários que não estão aprovados no sistema  (`is_active`), a menos que quem fez a requisição seja um *superusuário* ou um *staff* (respectivamente, `is_staff` e `is_superuser`), nesse caso nenhum filtro é aplicado na busca.

- /api/users/

Requisição POST que cria usuários, que por padrão tem `is_active = False`. Assim que é feita, um código de verificação é enviado para o e-mail da conta recém criada.

- /api/users/{id}/

Requisição GET que retorna um usuário pelo ID. Apenas usuários authenticados tem permissão de fazer essa requisição. São filtrados da busca, usuários que não estão aprovados no sistema  (`is_active`), a menos que quem fez a requisição seja um *superusuário* ou um *staff* (respectivamente, `is_staff` e `is_superuser`), nesse caso nenhum filtro é aplicado na busca.

- /api/users/{id}/

Requisição PATCH que atualiza um usuário pelo ID. A senha e o e-mail são bloqueados, tendo *endpoints* próprios.

- /api/users/{id}/

Requisição DELETE que desativa um usuário pelo ID. O usuário não é apagado do banco, o campo `is_active` é atualizado para `False`.

- /api/users/email_change_request/

Requisição POST que envia um código de mudança de e-mail para o novo e-mail do usuário.

- /api/users/email_change_confirm/

Requisição POST que confirma a mudança de email.

- /api/users/email_change_verify/

Requisição POST que apenas verifica o código de verificação sem alterar dados no banco.

- /api/users/login/

Requisição POST que cria uma sessão no Django e atualiza o cliente com *cookies*.

- /api/users/logout/

Requisição POST que apaga a sessão do usuário e apaga os *cookies* no cliente.

- /api/users/password_reset_request/

Requisição POST que envia um código de redefinição de senha para o e-mail do usuário.

- /api/users/password_reset_confirm/

Requisição POST que confirma a troca de senha.

- /api/users/password_reset_verify/

Requisição POST que apenas verifica o código de verificação sem alterar dados no banco.

- /api/users/email_verification_verify/

Requisição POST que apenas verifica o código de verificação de email.

- /api/users/email_verification_confirm/

Requisição POST que confirma a existência do e-mail do usuário.

## Lista de Tarefas

- [ ] Logout assim que e-mail ou senha são alterados.
- [ ] Template visual para os códigos enviados por e-mail. Bem como adição de perfil de envio de códigos por e-mail, na configuração  MAILERS.
- [ ] Adicionar *docstrings* nas classes e funções.
- [ ] Melhorar uso do drf-spectacular.
- [ ] Melhorar caminho das *urls*  (usar *kebab-case* ou outro, invés de *snake_case*).
