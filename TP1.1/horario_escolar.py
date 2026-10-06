# /// script
# dependencies = ["marimo"]
# requires-python = ">=3.14"
# ///

import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Relatório: Otimização de Horários Escolares

    ## 1. Importação de Bibliotecas e Configuração Inicial

    O primeiro passo do nosso código consiste em importar as ferramentas fundamentais para a manipulação de dados e resolução do problema lógico:

    * **`os` e `sys`**: Módulos nativos do Python utilizados para gerir caminhos de diretórios. Garantem que o programa consegue localizar corretamente as pastas de dados (`dados/` e `dados_v2/`) em qualquer sistema operativo.
    * **`pandas` (`pd`)**: Biblioteca essencial para a leitura dos ficheiros CSV. Permite extrair a informação estruturada das turmas, disciplinas, salas e exceções, e mais tarde construir a tabela final do horário gerado.
    * **`ortools.sat.python.cp_model`**: O "cérebro" matemático do projeto. Esta biblioteca da Google permite-nos modelar o horário como um Problema de Satisfação de Restrições (Constraint Programming), criando variáveis para as aulas e aplicando as regras do enunciado
    """)
    return


@app.cell
def _():
    import sys, os
    sys.path.insert(0, os.path.abspath(".libs"))
    import pandas as pd
    from ortools.sat.python import cp_model

    return cp_model, os, pd


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 2. Leitura e Processamento dos Ficheiros CSV (`carregar_dados`)

    Nesta fase, tratamos do carregamento e normalização dos dados necessários para a construção do horário.

    A função `carregar_dados(pasta)` foi desenhada para ser **dinâmica**, aceitando a localização da pasta (ex: `"dados"` ou `"dados_v2"`). Isto garante que o código cumpre o requisito de não ter dados fixos (*hardcoded*).

    ### Ficheiros Carregados:
    1. **`turmas.csv`**: Lista de turmas a ter aulas.
    2. **`disciplinas.csv`**: Cursos, carga horária semanal, docentes associados, sinalização de período duplo e necessidade de salas especiais.
    3. **`salas.csv`**: Inventário e tipos de salas disponíveis.
    4. **`disponibilidade_excecoes.csv`**: Restrições de horário dos professores.

    ### Mapeamento Temporal (Cálculo de *Slots*):
    Para simplificar a formulação matemática do solver, convertemos o calendário de 5 dias úteis e 5 períodos diários num sistema contínuo de **25 slots** ($0$ a $24$):
    * **Segunda-feira**: Slots 0 a 4
    * **Terça-feira**: Slots 5 a 9
    * **Quarta-feira**: Slots 10 a 14
    * **Quinta-feira**: Slots 15 a 19
    * **Sexta-feira**: Slots 20 a 24

    A conversão automática é feita através da fórmula:
    $$\text{slot} = (\text{dia\_map}[\text{dia}] \times 5) + (\text{período} - 1)$$
    """)
    return


@app.cell
def _(os, pd):
    def carregar_dados(pasta = "dados"):
        turmas_df = pd.read_csv(os.path.join(pasta, "turmas.csv"))
        disciplinas_df = pd.read_csv(os.path.join(pasta, "disciplinas.csv"))
        salas_df = pd.read_csv(os.path.join(pasta, "salas.csv"))
        disponibilidade_df = pd.read_csv(os.path.join(pasta, "disponibilidade_excecoes.csv"))

        dias_map = {"Seg": 0, "Ter": 1, "Qua": 2, "Qui": 3, "Sex": 4}
        disponibilidade_df["slot"] = disponibilidade_df.apply( # Cria uma nova coluna chamada slot na tabela das disponiblidade_excecoes.
            # Apply aplica uma operação ao dados e como o axis = 1 aplica essa opoeração linha a linha.
            lambda r: dias_map[r["dia"]] * 5 + (int(r["periodo"]) - 1), axis = 1
            # R é a linha que o apply está a ler no momento
            # Aqui estamos a supor que a semana está organizada em 25 tempos ou slots contínuos.
            # Segunda Feira tem os slots 0,1,2,3,4; Terça tem os slots 5,6,7,8,9...
        )

        return turmas_df, disciplinas_df, salas_df, disponibilidade_df

    return (carregar_dados,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 3. Criação de Blocos e Variáveis de Decisão do Solver

    Antes de aplicar as restrições, o programa transforma a carga horária das disciplinas em **blocos de aula** e cria as respetivas **variáveis de decisão** no modelo do OR-Tools (`CpModel`).

    ### 3.1. Divisão em Blocos de Aula
    * Cada disciplina é desdobrada em blocos consoante a sua carga semanal e a indicação de período duplo (`duplo_periodo`):
      * **Aulas simples (`duplo = False`)**: Duração de 1 slot.
      * **Aulas duplas (`duplo = True`)**: Duração de 2 slots consecutivos.
    * Cada bloco de aula recebe um identificador único no formato `Turma_Disciplina_Bloco` (ex: `10A_Matematica_0`).

    ### 3.2. Definição das Variáveis no CP-SAT
    Para cada bloco $b$, são definidas três variáveis principais:
    1. **`start_var`**: Slot de início da aula.
       * *Validação de limite*: Se a aula tiver duração de 2 tempos, é impedida de começar no último período do dia (slots 4, 9, 14, 19, 24), evitando que uma aula fique dividida entre dois dias diferentes.
    2. **`end_var`**: Slot de término da aula ($\text{start} + \text{duração}$).
    3. **`interval_var`**: Variável do tipo `NewIntervalVar` que encapsula o início, a duração e o fim do bloco. Esta estrutura é a base utilizada pelo solver para validar sobreposições.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 4. Implementação das Restrições Hard (R1 a R7)

    Para garantir um horário válido e exequível, aplicam-se restrições lógicas fundamentais sobre as variáveis de decisão:

    ### 4.1. Ausência de Sobreposição de Turmas e Professores (R1 e R5)
    Utiliza-se o método estático `model.AddNoOverlap` sobre os intervalos de tempo definidos:
    * **R1 (Turmas)**: Uma turma só pode frequentar uma aula de cada vez.
    * **R5 (Professores)**: Um docente não pode estar alocado a duas turmas em simultâneo.

    ### 4.2. Indisponibilidade de Professores (R6)
    Para cada restrição presente em `disponibilidade_excecoes.csv`:
    * Garante-se que `start != slot_indisponivel`.
    * Caso a aula seja **dupla** (duração = 2), adiciona-se também a restrição `start != slot_indisponivel - 1`, impedindo que a segunda metade do bloco coincida com o horário indisponível.

    ### 4.3. Limite Diário de Disciplinas por Turma (R3)
    Para evitar a concentração da mesma disciplina no mesmo dia:
    * Associa-se uma variável booleana (`no_dia`) a cada bloco para verificar se a aula ocorre num determinado dia (5 slots).
    * Aplica-se a regra de que o somatório de aulas da mesma disciplina num único dia para uma determinada turma tem de ser $\le 1$.

    ### 4.4. Capacidade e Tipos de Salas (R7)
    Garante-se que a procura por salas nunca excede a oferta física da escola:
    * Mapeia-se o número de salas disponíveis por tipo (ex: `normal`, `laboratorio`).
    * Para cada slot $s$, avalia-se através da variável booleana `em_curso` se cada aula está a decorrer nesse instante.
    * Garante-se que o somatório de aulas ativas num slot para um dado tipo de sala é menor ou igual ao número total de salas desse tipo existente na instituição.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 5. Resolução Incremental e Minimização de Alterações (R9)

    O requisito **R9** exige a capacidade de atualizar um horário previamente existente ($H_0$) quando surgem alterações na estrutura escolar (novos dados em `dados_v2`), gerando um novo horário ($H_1$) com o **mínimo de alterações possível** para alunos e professores.

    ### 5.1. Sugestões ao Solver (`AddHint`)
    Para otimizar o tempo de pesquisa e manter a estabilidade do horário, o solver utiliza as posições atribuídas no horário base $H_0$ como ponto de partida (*warm start*):
    * `model.AddHint(vars_bloco[b_id]["start"], slot_antigo)`

    ### 5.2. Controlo e Minimização de Mudanças
    Para quantificar e conter o impacto das alterações:
    1. Para cada aula que já existia no horário base $H_0$, define-se uma variável booleana `mudou`.
    2. A variável assume o valor `1` se o novo slot for diferente do anterior, e `0` se a aula mantiver o mesmo horário.
    3. O modelo estabelece como **função objetivo** a minimização do somatório de mudanças:
       `model.Minimize(sum(mudancas))`

    Com esta abordagem, o CP-SAT garante que o novo horário $H_1$ cumpre todas as restrições atualizadas, reordenando estritamente as aulas indispensáveis.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 6. Execução, Medição de Desempenho e Validação Automática

    Nesta secção final, executa-se o fluxo completo do gerador de horários, mede-se a eficiência da construção incremental e valida-se rigorosamente a conformidade das soluções obtidas.

    ### 6.1. Fluxo Incremental ($H_0 \rightarrow H_1$) e Medição de Tempos
    1. **Horário Base ($H_0$)**: Gerado a partir do conjunto de dados inicial localizado na pasta `dados/`.
    2. **Horário Incremental ($H_1$)**: Gerado a partir de `dados_v2/` (com novas exceções de disponibilidade de professores), fornecendo $H_0$ ao solver como referência.
    3. **Métricas de Desempenho**:
       * **Tempo de Execução**: Registo dos segundos necessários para calcular $H_0$ e $H_1$.
       * **Taxa de Alteração**: Contagem direta das aulas cujo `slot_inicio` sofreu alteração entre $H_0$ e $H_1$, demonstrando o impacto mínimo na rotina escolar.

    ### 6.2. Validador Automático Post-Hoc (`validar_horario`)
    Para garantir a integridade dos resultados independentemente do solver, foi desenvolvida a função de verificação automática:
    * **Desdobramento de Aulas Duplas**: Converte blocos de duração 2 em registos explícitos para cada período individual ocupado.
    * **Teste R1 (Turmas)**: Agrupa por `(dia, período, turma)` e confirma a inexistência de sobreposição de aulas.
    * **Teste R5 (Professores)**: Agrupa por `(dia, período, professor)` e confirma que nenhum docente tem duas aulas no mesmo instante.

    ### 6.3. Apresentação dos Resultados
    A visualização final do horário é integrada na interface interativa do Marimo através da componente `mo.ui.table(H1)`, permitindo ordenação e filtragem dinâmica das aulas geradas.
    """)
    return


@app.cell
def _(cp_model, pd):
    def resolver_horario(turmas_df, disciplinas_df, salas_df, excecoes_df,horario_base=None):
        model = cp_model.CpModel()

        DIAS = 5
        PERIODOS = 5
        SLOTS = DIAS * PERIODOS


        blocos = []
        for _, tur in turmas_df.iterrows():
            t_nome = tur["turma"]
            for _, disc in disciplinas_df.iterrows():
                p_nome = disc["professor"] # Pegar os dados de todas as disciplinas...
                d_nome = disc["disciplina"]
                carga = int(disc["carga_semanal"])
                duplo = str(disc["duplo_periodo"]).strip().lower() == "sim"
                sala_esp = (
                    str(disc["sala_especial"]).strip()
                    if pd.notna(disc["sala_especial"])
                    else "normal"
                )

                num_blocos = carga // 2 if duplo else carga # O numero de blocos é decidido conforme a multiplicidade? da carga
                # Se for para dividir em blocos duplos uma cadeira com 6 tempos, queremos 3 blocos de 2 horas
                duracao = 2 if duplo else 1
                # duração de cada bloco para a disciplina atual

                for b in range(num_blocos):
                    blocos.append(
                        {
                            "id": f"{t_nome}_{d_nome}_{b}",
                            "turma": t_nome,
                            "disciplina": d_nome,
                            "professor": p_nome,
                            "duracao": duracao,
                            "sala_especial": sala_esp,
                        }
                    )

        vars_bloco = {}
        for b in blocos:
            b_id = b["id"]
            dur = b["duracao"]

            slots_validos = [
                # Se a duração de um bloco for == 2, não pode começar no ultimo tempo do dia
                s for s in range(SLOTS) if not (dur == 2 and (s % PERIODOS == PERIODOS - 1))
            ]

            start_var = model.NewIntVarFromDomain( # Definição da variável para o slot de início
                cp_model.Domain.FromValues(slots_validos), f"start_{b_id}"
            )
            end_var = model.NewIntVar(0, SLOTS, f"end_{b_id}")

            interval_var = model.NewIntervalVar( # Variável de intervalo (start + duração = end)
                start_var, dur, end_var, f"interval_{b_id}"
            )

            vars_bloco[b_id] = {
                "start": start_var,
                "end": end_var,
                "interval": interval_var,
                "info": b,
            }

        # Aplicação das restrições

        #R1: Não haver sobreposição de aulas na mesma turma
        for t in turmas_df["turma"].unique():
            intervalos_turma = [ v["interval"] for v in vars_bloco.values() if v["info"]["turma"] == t] # filtra os intervalos de tempo que pertence a turma t
            model.AddNoOverlap(intervalos_turma) # Garante que a turma t so tem 1 aula de cada vez

        #R5: Não haver sobreposição de aulas no mesmo professor
        for p in disciplinas_df["professor"].unique():
            intervalos_prof = [ v["interval"] for v in vars_bloco.values() if v["info"]["professor"] == p] # filtra as aulas que têm como docente o professor p
            model.AddNoOverlap(intervalos_prof) # Não deixa um professor estar em duas aulas ao mesmo tempo

        #R6: Indisponiblidade de Professores (Exceções)
        for _, exc in excecoes_df.iterrows(): # Percorrer a tabela de exceções
            prof_exc = exc["professor"] # guarda o nome do professor com restrição
            slot_indisponivel = exc["slot"] # e o numero do slot que ele nao pode dar aula

            #Encontrar todas as aulas deste prof
            for v in vars_bloco.values(): # Percorrer todas as aulas
                if v["info"]["professor"] == prof_exc: # Para encontrar as que pertencem a esse professor
                    dur = v["info"]["duracao"]
                    model.Add(v["start"] != slot_indisponivel) # O começo da aula não pode coincidir com o slot indisponivel do professor

                    if dur == 2 and slot_indisponivel > 0:
                        model.Add(v["start"] != slot_indisponivel - 1) # Se a aula for dupla, o calculo tem que ser feito com o slot anterior ao slot da exceção

        #R3: No maximo 1 bloco da mesma disciplina por dia por turma
        DIAS = 5
        PERIODOS = 5

        for t in turmas_df["turma"].unique():
            for d_nome in disciplinas_df["disciplina"].unique():
                blocos_td = [v for v in vars_bloco.values() if v["info"]["turma"] == t and v["info"]["disciplina"] == d_nome] # Seleciona as aulas do dicionario que
                # pertencem a essa turma t e disciplina d_nome

                for dia in range(DIAS):
                    aulas_no_dia = []
                    inicio_dia = dia * PERIODOS
                    fim_dia = inicio_dia + PERIODOS - 1

                    for v in blocos_td: # Pega em todas as aulas de um disciplina especifica
                        no_dia = model.NewBoolVar(f"no_dia_{v['info']['id']}_dia{dia}") # Criação duma variavel do tipo boolean com o valor:
                        # "1 se A aula calhou neste dia
                        # 0 se A aula não calhou neste dia"

                        model.AddLinearExpressionInDomain(v["start"], cp_model.Domain.FromIntervals([[inicio_dia, fim_dia]]), # Obriga a hora de inicio da aula
                                                            # estar entre o inicio e fim do dia
                        ).OnlyEnforceIf(no_dia) # Apenas se no_dia for 1 
                        model.AddLinearExpressionInDomain(
                            v["start"], cp_model.Domain.FromIntervals([[0,inicio_dia - 1], [fim_dia + 1, 24]] # A hora de inicio da aula tem de estar fora deste dia quando:
                            ),
                        ).OnlyEnforceIf(no_dia.Not()) # A variavel no_dia = 0

                        aulas_no_dia.append(no_dia) # Guarda a variavel no_dia na lista do dia

                    model.Add(sum(aulas_no_dia) <= 1) # Proibe que haja mais do que uma aula duma certa disciplina no mesmo dia

        #R7: Capacidade e tipos de salas de aula
        col_tipo = "tipo_sala" if "tipo_sala" in salas_df.columns else "tipo"
        capacidade_salas = salas_df[col_tipo].value_counts().to_dict() # Seleciona a coluna dos tipos de sala, conta quantas vezes cada tipo aparece e converte num dicionario
        # "{'normal': 6, 'Lab':2 ...}"

        for s in range(SLOTS): # Percorre os slots todos da semana
            for tipo_sala, max_salas in capacidade_salas.items(): # Pega em cada par do dicionario capacidade_salas
                aulas_no_slot = [] # Criação duma lista vazia para acumular os "interruptores" de todas as aulas que estiverem a acontecer no slot s para aquele tipo_sala

                for v in vars_bloco.values():

                    if v["info"]["sala_especial"] == tipo_sala: # So avança se a aula precisar exatamente do tipo_sala que estamos a analisar neste ciclo
                        dur = v["info"]["duracao"] # extrai a duração dessa aula

                        em_curso = model.NewBoolVar(f"em_curso_{v['info']['id']}_s{s}") # "Esta aula esta a ocupar espaço no slot s? 1:SIM 0:NAO"

                        if dur == 1:
                            model.Add(v["start"] == s).OnlyEnforceIf(em_curso) # Se em_curso == 1 então a hora de inicio da aula tem de ser extamanete igual ao slot s
                            model.Add(v["start"] != s).OnlyEnforceIf(em_curso.Not()) # Se a aula não estiver a decorrer neste slot, então o começo tem de ser diferente do slot s
                        else:
                            if s == 0:
                                model.Add(v["start"] == 0).OnlyEnforceIf(em_curso) # A aula so pode estar a decorrer no slot 0 se tiver começado no slot 0
                                model.Add(v["start"] != 0).OnlyEnforceIf(em_curso.Not())
                            else:
                                model.AddLinearExpressionInDomain(v["start"], cp_model.Domain.FromValues([s - 1, s])
                                                                  ).OnlyEnforceIf(em_curso) # Se em_curso == 1 então o começo da aula tem de ser igual a s - 1 ou igual a s

                                slots_fora = [x for x in range(SLOTS) if x not in (s - 1, s)] # Cria uma lista com  todos os slots da semana exceto o s e o s-1
                                model.AddLinearExpressionInDomain(
                                    v["start"], cp_model.Domain.FromValues(slots_fora) # Se a aula não estiver a decorrer no slot s, a hora de inicio tem de estar
                                    # dentro da lista slots_fora
                                ).OnlyEnforceIf(em_curso.Not())

                        aulas_no_slot.append(em_curso) # Adicionar o valor de em_curso para contar as aulas que estao a usar este tipo de sala no slot s

                model.Add(sum(aulas_no_slot) <= max_salas) # Garante que o total de aulas a decorrer em simultâneo nunca ultrapassa a quantidade se salas disponiveis na escola

        #R9: Dicas de horario anterior
        if horario_base is not None:
            mudancas = []
            for _, row in horario_base.iterrows():
                b_id = row["id_bloco"]
                if b_id in vars_bloco:
                    slot_antigo = int(row["slot_inicio"])
                    # Dica para começar a procurar aqui
                    model.AddHint(vars_bloco[b_id]["start"], slot_antigo) 
            
                    # Variável para saber se esta aula mudou de sítio (1) ou não (0)
                    mudou = model.NewBoolVar(f"mudou_{b_id}")
                    model.Add(vars_bloco[b_id]["start"] == slot_antigo).OnlyEnforceIf(mudou.Not())
                    model.Add(vars_bloco[b_id]["start"] != slot_antigo).OnlyEnforceIf(mudou)
                    mudancas.append(mudou)
    
            # OBJETIVO: Dizemos ao solver para minimizar o total de aulas que mudaram de slot
            model.Minimize(sum(mudancas))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30.0 # Definir um tempo limite para a procura de solução para não bloquear

        status = solver.Solve(model) # Calculo das restrições. 

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE): # Se o solver encontrou uma solução perfeita ou valida que cumpre todas as regras
            dias_nome = ["Seg", "Ter", "Qua", "Qui", "Sex"]
            resultado = []

            for b_id, v in vars_bloco.items():
                slot_inicio = solver.Value(v["start"]) # Extrai o numero inteiro final (entre 0 e 24) que o solver atribuiu a variavel de inicio da aula
                duracao = v["info"]["duracao"]

                dia_idx = slot_inicio // PERIODOS # Converter slots para calendario normal (0 // 5) = 0 (segunda feira ...)
                periodo_num = (slot_inicio % PERIODOS) + 1

                resultado.append({
                    "id_bloco": b_id,
                    "turma": v["info"]["turma"],
                    "disciplina": v["info"]["disciplina"],
                    "professor": v["info"]["professor"],
                    "sala_especial": v["info"]["sala_especial"],
                    "dia": dias_nome[dia_idx],
                    "periodo": periodo_num,
                    "duracao": duracao,
                    "slot_inicio": slot_inicio,
                })
            return pd.DataFrame(resultado) # Devolve os dados organizados num dataframe do pandas, pronto para ser visualizado em tabela ou exportado para csv
        else:
            print("Nao foi possivel encontrar uma solução valida.")
            return None

    return (resolver_horario,)


@app.cell
def _(carregar_dados, resolver_horario):
    import time

    print("--- GERAR HORÁRIO INICIAL (H0) ---")
    turmas, disc, salas, exc = carregar_dados("dados")

    t0_start = time.time()
    H0 = resolver_horario(turmas, disc, salas, exc)
    t0_total = time.time() - t0_start
    print(f"H0 gerado em {t0_total:.2f} segundos.\n")

    print("--- GERAR HORÁRIO INCREMENTAL (H1) ---")
    # Usa a pasta dados_v2 que o professor menciona
    turmas_v2, disc_v2, salas_v2, exc_v2 = carregar_dados("dados_v2") 

    t1_start = time.time()
    # Passamos o H0 como base para o programa tentar manter igual
    H1 = resolver_horario(turmas_v2, disc_v2, salas_v2, exc_v2, horario_base=H0)
    t1_total = time.time() - t1_start

    # Contar diferenças
    mudancas_count = 0
    if H0 is not None and H1 is not None:
        comparacao = H0.merge(H1, on="id_bloco", suffixes=("_h0", "_h1"))
        mudancas_count = (comparacao["slot_inicio_h0"] != comparacao["slot_inicio_h1"]).sum()

    print(f"H1 gerado em {t1_total:.2f} segundos.")
    print(f"Total de aulas que tiveram de mudar de sítio: {mudancas_count}")
    return (H1,)


@app.cell
def _(pd):
    def validar_horario(df):
        erros = []
        # Como algumas aulas duram 2 tempos (duplo_periodo), temos de as "desdobrar" para verificar sobreposições corretamente
        slots_ocupados = []
        for _, row in df.iterrows():
            slots_ocupados.append(row.to_dict())
            if row['duracao'] == 2:
                row2 = row.copy()
                row2['periodo'] += 1
                row2['slot_inicio'] += 1
                slots_ocupados.append(row2.to_dict())
        
        df_exp = pd.DataFrame(slots_ocupados)

        # Testar R1: Uma turma não pode ter duas aulas no mesmo dia e período
        for (dia, per, turma), grupo in df_exp.groupby(['dia', 'periodo', 'turma']):
            if len(grupo) > 1: 
                erros.append(f"ERRO R1: A turma {turma} tem {len(grupo)} aulas no dia {dia}, período {per}")
        
        # Testar R5: Um professor não pode dar duas aulas no mesmo dia e período
        for (dia, per, prof), grupo in df_exp.groupby(['dia', 'periodo', 'professor']):
            if len(grupo) > 1: 
                erros.append(f"ERRO R5: O {prof} tem {len(grupo)} aulas no dia {dia}, período {per}")
        
        if not erros:
            print("✅ SUCESSO: O horário gerado é VÁLIDO! Passou no teste automático de sobreposições (R1 e R5).")
        else:
            for e in erros: print(e)


    return (validar_horario,)


@app.cell
def _(H1, validar_horario):
    validar_horario(H1)
    return


@app.cell
def _(H1):
    mo.ui.table(H1)
    return


if __name__ == "__main__":
    app.run()
