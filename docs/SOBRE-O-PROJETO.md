# Backup Manager — Sistema Traz Valor

### Apresentação do projeto em linguagem simples

*Situação em 13/11/2026*

---

## 1. Em poucas palavras

O **Backup Manager** é um sistema que faz **cópias de segurança automáticas** dos bancos de dados da empresa.

Um **banco de dados** é onde um sistema guarda as suas informações: cadastros de clientes, notas, pedidos, usuários e assim por diante. Se esse banco for perdido (por um defeito no servidor, um erro humano, um ataque de vírus ou um problema na hospedagem), as informações vão junto.

O Backup Manager resolve isso: em dias e horários combinados, ele **tira uma "fotografia" completa do banco**, guarda essa cópia de forma **protegida (criptografada)** e mostra num painel se tudo deu certo. Se um dia for preciso recuperar os dados, basta **baixar a cópia** pelo próprio painel.

> **Comparação do dia a dia:** é como ter alguém que, toda terça e sexta no fim do expediente, tira cópia de todos os documentos importantes do escritório, guarda num cofre e anota num caderno o que foi copiado e se deu tudo certo.

---

## 2. Por que o projeto existe

Antes, a empresa dependia de cópias feitas manualmente ou de soluções espalhadas, sem um lugar único para ver:

- **quais** bancos estão protegidos;
- **quando** foi a última cópia de cada um;
- **se** a cópia deu certo ou falhou, e **por quê**.

O objetivo foi criar **um único painel**, simples de usar, onde qualquer responsável consegue cadastrar os bancos, escolher os dias de cópia e acompanhar tudo, sem precisar de conhecimento técnico no dia a dia.

---

## 3. Como o sistema é construído (as "linguagens" utilizadas)

Um sistema como este é formado por partes que conversam entre si, mais ou menos como numa empresa: tem a recepção, o escritório e a equipe que executa o serviço. Cada parte usa uma linguagem de programação adequada à sua função.

| Parte do sistema | Comparação | Tecnologia usada | O que faz |
|---|---|---|---|
| **Painel (telas)** | A recepção, onde você é atendido | **Vue.js** (JavaScript), com HTML e CSS | São as telas que você vê no navegador: menus, botões, formulários e avisos |
| **Servidor do painel** | O escritório, que confere e registra os pedidos | **Laravel** (PHP) | Confere login e senha, valida o que foi digitado, guarda os cadastros e libera os downloads |
| **Executor dos backups** | A equipe que vai a campo fazer o serviço | **Python** | Fica sempre ligado. Na hora marcada, conecta no banco, faz a cópia, compacta, criptografa e guarda |
| **Banco de controle** | O caderno de anotações | **PostgreSQL** | Guarda os cadastros do próprio sistema: usuários, bancos cadastrados, agendamentos e o histórico de cópias |
| **"Caixas" de instalação** | Um contêiner de mudança, já montado | **Docker** | Empacota todas as partes, para o sistema funcionar igual em qualquer computador ou servidor |

### Quais bancos ele consegue copiar

| Tipo de banco | Onde costuma ser usado |
|---|---|
| **MySQL** | A maioria dos sites e sistemas em hospedagens (ex.: uni5, KingHost) |
| **PostgreSQL** | Sistemas mais robustos |
| **SQLite** | Sistemas menores, em que o banco é um único arquivo. Pode estar no próprio computador ou em outro servidor (buscado com segurança, via SSH) |

---

## 4. Linha do tempo: do início até hoje

### Origem

O projeto começou como um sistema simples, feito apenas em **PHP**. Ele funcionava, mas era limitado e difícil de evoluir. Foi então **refeito do zero** com tecnologias mais modernas (Laravel, Python e Vue), separando bem as telas, as regras e a execução das cópias.

### 09/11/2026: primeira versão da nova plataforma

- Painel com login, cadastro de bancos **MySQL**, agendamentos, histórico e configurações.
- Cópias **compactadas e criptografadas** (protegidas com a mesma família de criptografia usada por bancos e governos).
- Regras de horário: cópias automáticas **só depois das 17h** (horário de Cuiabá), para não pesar no horário comercial.
- Retenção: o sistema guarda as últimas cópias de cada banco e apaga as mais antigas sozinho.
- Testes automáticos para conferir as partes principais.
- Nessa versão, o "caderno de anotações" do sistema era um arquivo simples (SQLite).

### 12/11/2026: troca do banco de controle

- O "caderno de anotações" passou a ser um **PostgreSQL** próprio, mais robusto para uso contínuo.
- As tabelas do sistema receberam nomes padronizados (com o prefixo `sis_`).

### 12 e 13/11/2026: melhorias feitas a partir do uso real

Ao colocar o sistema para copiar os bancos de verdade, apareceram situações reais que foram tratadas uma a uma:

1. **Mais tipos de banco:** além do MySQL, o sistema passou a copiar **PostgreSQL** e **SQLite**. No cadastro há um campo para escolher o tipo.
2. **SQLite em outro servidor:** quando o arquivo SQLite está em outro computador, o sistema o busca com segurança (via SSH) usando o endereço, o usuário e a senha informados.
3. **Textos maiores:** as letras do painel foram aumentadas para facilitar a leitura. O menu lateral foi mantido no tamanho original.
4. **Nome padrão:** exemplos e textos com o nome antigo ("DY") passaram a usar "Traz Valor".
5. **Servidores sem criptografia na conexão:** algumas hospedagens não aceitam conexão criptografada. O sistema explica como ajustar isso no cadastro.
6. **Bancos antigos (tabelas MyISAM):** bancos de sistemas legados usam um formato antigo de tabela. Foi criado um modo de cópia próprio para eles, que trava rapidamente **só aquele banco** enquanto copia, sem afetar os demais.
7. **Correção de um erro na cópia MySQL:** um ajuste de configuração impedia a cópia de começar. Foi corrigido.
8. **Download em ZIP:** a cópia agora é baixada como um arquivo **.zip** com o banco dentro, pronto para usar. No servidor ela continua guardada protegida.
9. **Download sem limite de tempo:** bancos muito grandes podem levar horas para baixar. O download passou a começar na hora e a ir sendo montado enquanto baixa, sem tempo máximo.
10. **Dicas quando algo dá errado:** quando uma cópia falha, o painel explica **o que aconteceu, o que fazer e onde**, com um botão que abre a tela certa e destaca em amarelo os campos a corrigir.
11. **Agendamento acompanha o banco:** pausar um banco pausa automaticamente os agendamentos dele, e reativar o banco os reativa.
12. **Manual de instalação:** um guia detalhado (arquivo `README.md`) ensina a instalar e testar o sistema em qualquer computador.

### Onde o projeto está hoje

- O sistema está **funcionando** e já fez **cópias reais com sucesso** dos bancos cadastrados (Dy Isenções e Traz Valor).
- Todas as funções descritas neste documento estão prontas e cobertas por testes automáticos.
- **Próximos passos recomendados:**
  - fazer, pelo menos uma vez por mês, um **teste de restauração**, colocando uma cópia num banco separado para confirmar que ela abre e está completa;
  - guardar uma **cópia das chaves de segurança** fora do servidor (sem elas as cópias não podem ser abertas);
  - para uso fora da rede local, publicar o painel com **endereço seguro (HTTPS)**;
  - configurar o **aviso por e-mail** quando uma cópia falhar.

---

## 5. As telas do sistema, uma a uma

### 5.1 Tela de login

É a porta de entrada. Pede **e-mail** e **senha**. Só pessoas com acesso cadastrado entram. A sessão é protegida e expira após um período sem uso.

### 5.2 Menu lateral

Fica sempre à esquerda e dá acesso às cinco áreas do sistema:

- **Visão geral**
- **Bancos de dados**
- **Agendamentos**
- **Histórico**
- **Configurações**

No rodapé do menu aparecem o nome de quem está conectado e o botão **Sair**. No topo da tela aparece o horário usado pelo sistema (**Cuiabá**).

### 5.3 Visão geral (página inicial)

É o **resumo** da situação. Mostra:

- **Quatro números principais:** quantos bancos estão cadastrados, quantas rotinas automáticas estão ativas, quantas cópias estão disponíveis e quantas falharam nas últimas 24 horas.
- **Bancos monitorados:** a lista dos bancos com a situação da última cópia (*Concluído*, *Falhou*, *Na fila*...) e um botão **Testar** para fazer uma cópia na hora.
- **Sua programação:** os próximos horários de cópia automática.
- **Aviso do executor:** se a parte que faz as cópias parar de responder, aparece um alerta amarelo no topo.

### 5.4 Bancos de dados

Lista os bancos que o sistema protege. Cada banco aparece num cartão com:

- nome, tipo (MySQL, PostgreSQL ou SQLite) e situação (**Ativo** ou **Pausado**);
- endereço do servidor, nome do banco e tipo de segurança da conexão;
- data e resultado da última cópia;
- botão **Editar conexão**, para alterar os dados;
- botão **Gerar backup de teste**, para fazer uma cópia na hora.

Se a última cópia falhou, o cartão mostra o **quadro amarelo de dicas** com o que fazer.

**Formulário "Adicionar banco" / "Editar banco":**

| Campo | O que significa |
|---|---|
| Nome do banco | Nome que aparece no painel (ex.: *Traz Valor*) |
| Tipo de banco | MySQL, PostgreSQL ou SQLite |
| Host e Porta | O "endereço" do servidor onde o banco está |
| Banco de dados | O nome do banco dentro do servidor. No SQLite, é o arquivo |
| Usuário e Senha | O acesso ao banco. A senha fica guardada protegida e nunca é mostrada de volta |
| Conexão TLS | Se a conversa com o servidor é criptografada. Algumas hospedagens não aceitam; nesse caso, usa-se "Sem TLS" |
| Arquivo CA | Certificado de segurança extra (opcional, raramente usado) |
| Consistência do backup | Como a cópia é feita para sair "inteira", sem dados pela metade. Bancos antigos usam o modo de "bloqueio das tabelas" |
| Banco ativo | Liga ou desliga as cópias deste banco. Desligar também pausa os agendamentos dele |

### 5.5 Agendamentos

Aqui se define **quando** cada banco é copiado automaticamente. Cada agendamento aparece num cartão com:

- o nome do banco;
- o **horário** (sempre entre 17:01 e 23:59, horário de Cuiabá);
- os **dias da semana** escolhidos, destacados;
- a situação (**Ativo** ou **Pausado**). Se o banco estiver desligado, o cartão avisa e mostra onde religar.

O botão **Novo agendamento** abre um formulário simples: escolher o banco, clicar nos dias da semana e escolher o horário.

> Os bancos são copiados **um de cada vez**. Se dois estiverem marcados para o mesmo horário, o segundo começa assim que o primeiro terminar.

### 5.6 Histórico

É o **registro de todas as cópias**, as automáticas e as de teste. Para cada uma mostra:

- qual banco e se foi **agendamento** ou **teste manual**;
- quando foi pedida e quando terminou;
- o resultado: **Na fila**, **Em execução**, **Concluído**, **Falhou**, **Expirado** (cópia antiga já apagada pela retenção) ou **Cancelado**;
- o tamanho do arquivo;
- o botão de **download** (ícone de seta), que baixa a cópia em **.zip**.

Quando uma cópia **falha**, aparece logo abaixo um **quadro amarelo** explicando, em português simples, o que aconteceu, com o passo a passo e um botão **Corrigir configuração do banco**.

Há também uma **busca** (por nome do banco ou situação) e o item **Detalhes da execução**, com as informações técnicas. A tela se atualiza sozinha a cada 10 segundos.

### 5.7 Configurações

Ajustes gerais que valem para as próximas cópias:

| Opção | O que significa |
|---|---|
| Backups mantidos por banco | Quantas cópias guardar de cada banco. As mais antigas são apagadas sozinhas (padrão: 4) |
| Tempo máximo do dump | Quanto tempo uma cópia pode levar antes de ser considerada travada (padrão: 6 horas) |
| Reserva mínima de disco | Espaço livre que precisa sobrar no servidor; se faltar, a cópia para por segurança |
| Exigir cópia externa | Manda uma segunda via de cada cópia para outro local (ex.: outro disco ou servidor) |

A tela também lembra da importância de guardar as **chaves de segurança** e mostra se o executor está conectado.

---

## 6. Segurança: como as cópias são protegidas

- **Senhas dos bancos** ficam guardadas criptografadas e **nunca** aparecem nas telas.
- **Cada cópia** é compactada e **criptografada** assim que é gerada. Mesmo que alguém pegue o arquivo no servidor, não consegue abrir sem a chave.
- **O painel** exige login, e as ações são protegidas contra uso indevido.
- **O download** entrega o banco já aberto, dentro de um .zip, para facilitar a recuperação. Por isso, **quem baixa deve guardar o arquivo em local seguro**.
- **As chaves de segurança** são criadas automaticamente na instalação. **Sem elas as cópias não podem ser abertas**, por isso devem ter uma cópia guardada fora do servidor.

---

## 7. Pequeno glossário

| Termo | Significado simples |
|---|---|
| **Backup** | Cópia de segurança |
| **Banco de dados** | Onde um sistema guarda as suas informações |
| **Servidor / Host** | O computador, geralmente na internet, onde o banco fica |
| **Agendamento** | Regra que diz em que dias e horário a cópia é feita sozinha |
| **Criptografia** | "Embaralhar" os dados com uma chave, para que só quem tem a chave consiga ler |
| **TLS** | Criptografia aplicada na conversa entre o sistema e o servidor do banco |
| **Executor (worker)** | A parte do sistema que fica ligada o tempo todo e faz as cópias |
| **Retenção** | Regra de quantas cópias antigas manter antes de apagar |
| **Restauração** | Usar uma cópia para recuperar os dados |
| **ZIP** | Formato de arquivo compactado, que se abre com um clique no Windows |
| **Docker** | Ferramenta que empacota o sistema para ele funcionar igual em qualquer máquina |
| **MyISAM** | Formato antigo de tabela usado por sistemas legados, que exige um modo de cópia especial |
